from types import SimpleNamespace

from apps.fraud.data.dataset import generate_fraud_dataset
from apps.fraud.data.sqlite_store import SQLiteFraudRepository
from apps.fraud.real import close_real_agent, create_real_agent
from core.knowledge.registry import KnowledgeSourceRegistry


class _Record:
    def single(self):
        return {"count": 1}

    def consume(self):
        return None


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def run(self, query, **parameters):
        return _Record()


class _Driver:
    def __init__(self):
        self.verify_calls = 0
        self.close_calls = 0

    def verify_connectivity(self):
        self.verify_calls += 1

    def session(self, **kwargs):
        return _Session()

    def close(self):
        self.close_calls += 1


def _agent_with_core_graph(driver):
    core_graph = SimpleNamespace(_driver=driver)
    core_registry = SimpleNamespace(
        get=lambda name: core_graph if name == "neo4j" else None
    )
    return SimpleNamespace(
        knowledge_graph_registry=core_registry,
        planner=SimpleNamespace(
            knowledge_source_registry=KnowledgeSourceRegistry(),
            knowledge_graph_registry=None,
        ),
        resource_router=SimpleNamespace(
            knowledge_graph_registry=None,
            knowledge_source_registry=None,
        ),
        execution_manager=SimpleNamespace(
            knowledge_graph_registry=None,
            knowledge_source_registry=None,
            graph_result_processor=None,
            knowledge_decision=None,
            policy=None,
        ),
        workflow_registry=SimpleNamespace(register=lambda workflow: None),
        policy=None,
    )


def test_real_composition_wires_sqlite_and_shared_neo4j_driver_without_mysql(
    monkeypatch, tmp_path
):
    from apps.fraud import real

    database = tmp_path / "fraud.db"
    repository = SQLiteFraudRepository(database)
    repository.initialize()
    repository.seed(generate_fraud_dataset())
    driver = _Driver()
    agent = _agent_with_core_graph(driver)
    monkeypatch.setattr(real, "get_config", lambda: SimpleNamespace(
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="local-test-password",
        neo4j_database="neo4j",
        neo4j_graph_name="neo4j",
        sql_database_path=str(database),
    ))
    monkeypatch.setattr(real.core_composition, "create_agent", lambda **kwargs: agent)

    composed = create_real_agent()

    assert composed is agent
    assert driver.verify_calls == 1
    assert composed.knowledge_graph_registry.get("customer_graph")._driver is driver
    assert composed.knowledge_graph_registry.get("fraud_graph")._driver is driver
    source = composed.execution_manager.knowledge_source_registry.get("business_db")
    assert source.backend.database_path == str(database)
    assert composed.planner.knowledge_source_registry is composed.execution_manager.knowledge_source_registry
    assert composed.planner.knowledge_graph_registry is composed.knowledge_graph_registry

    close_real_agent(composed)
    assert driver.close_calls == 1


def test_real_composition_refuses_unseeded_sqlite_without_creating_data(
    monkeypatch, tmp_path
):
    from apps.fraud import real

    database = tmp_path / "not-seeded.db"
    repository = SQLiteFraudRepository(database)
    repository.initialize()
    monkeypatch.setattr(real, "get_config", lambda: SimpleNamespace(
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="local-test-password",
        neo4j_database="neo4j",
        neo4j_graph_name="neo4j",
        sql_database_path=str(database),
    ))
    monkeypatch.setattr(
        real.core_composition,
        "create_agent",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not compose")),
    )

    try:
        create_real_agent()
    except RuntimeError as exc:
        assert "canonical SQLite fraud dataset" in str(exc)
    else:
        raise AssertionError("Expected real composition to reject an unseeded database.")

    assert repository.counts()["customers"] == 0
