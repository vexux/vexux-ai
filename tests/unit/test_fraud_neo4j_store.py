from apps.fraud.data.dataset import generate_fraud_dataset
from apps.fraud.data.neo4j_store import Neo4jFraudStore


class _Result:
    def __init__(self, query, parameters):
        self.query = query
        self.parameters = parameters

    def consume(self):
        return None

    def single(self):
        if "RETURN count(r)" in self.query:
            return {"count": len(self.parameters["rows"])}
        if "RETURN count(n)" in self.query:
            return {"count": 1}
        return None


class _Session:
    def __init__(self, driver):
        self.driver = driver

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def run(self, query, **parameters):
        self.driver.queries.append((query, parameters))
        return _Result(query, parameters)

    def execute_write(self, callback):
        return callback(self)


class _Driver:
    def __init__(self):
        self.queries = []
        self.database = None

    def session(self, **kwargs):
        self.database = kwargs.get("database")
        return _Session(self)

    def verify_connectivity(self):
        return None


def test_neo4j_constraints_precede_idempotent_canonical_seed_and_scope_reset():
    driver = _Driver()
    store = Neo4jFraudStore(driver, database="neo4j")
    store.verify_connection()
    store.seed(generate_fraud_dataset())

    constraint_queries = [
        query for query, _ in driver.queries if query.startswith("CREATE CONSTRAINT")
    ]
    assert len(constraint_queries) == 8
    first_write_index = next(
        index for index, (query, _) in enumerate(driver.queries)
        if query.startswith("UNWIND")
    )
    assert all(
        driver.queries.index((query, {})) < first_write_index
        for query in constraint_queries
    )
    customer_write = next(
        (query, parameters)
        for query, parameters in driver.queries
        if "MERGE (n:Customer" in query
    )
    assert customer_write[1]["rows"][0]["properties"]["vexux_dataset"] == "vexux_fraud"
    assert driver.database == "neo4j"

    store.require_seeded()
    store.reset()
    reset_queries = driver.queries[-2:]
    assert all("vexux_dataset = $dataset" in query for query, _ in reset_queries)
    assert all(params["dataset"] == "vexux_fraud" for _, params in reset_queries)


def test_neo4j_store_rejects_missing_driver():
    try:
        Neo4jFraudStore(None)
    except ValueError as exc:
        assert "driver is required" in str(exc)
    else:
        raise AssertionError("Expected missing driver validation.")
