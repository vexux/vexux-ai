import os

from rag.pipeline import RAGPipeline

from core.model_gateway.gateway import ModelGateway
from models.providers.mistral import MistralProvider
from models.providers.qwen import QwenProvider

from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool
from core.tools.string_formatter import StringFormatterTool
from core.tools.text_analyzer import TextAnalyzerTool
from core.context.context_manager import ContextManager
from core.knowledge.registry import KnowledgeSourceRegistry
from rag.knowledge_source import RAGKnowledgeSource
from core.policy.default import DefaultPolicy
from core.workflows.registry import WorkflowRegistry
from core.workflows.knowledge_grounded_answer import KnowledgeGroundedAnswerWorkflow

# Optional knowledge graph foundation (Phase 10)
from core.knowledge.graph_registry import KnowledgeGraphRegistry
from core.knowledge.inmemory_graph import InMemoryKnowledgeGraph
from core.knowledge.neo4j_graph import Neo4jKnowledgeGraph
from core.knowledge.sql_source import SQLKnowledgeSource
from core.knowledge.sqlite_backend import SQLiteBackend
from core.knowledge.resource_router import ResourceRouter

from agent.execution_manager import ExecutionManager
from agent.planner import Planner
from agent.agent import Agent

from agent.observer import Observer
from agent.decision import DecisionMaker
from agent.response_synthesizer import ResponseSynthesizer
from core.memory.registry import MemoryRegistry
from core.memory.sqlite_memory import SQLiteMemory
from core.orchestrator import Orchestrator
from core.specialized_agents import ResearchAgent, SpecializedAgentRegistry
from core.specialized_agents.llm_delegation_planner import LLMDelegationPlanner
from pathlib import Path


def create_agent():

    # -------------------------
    # Model
    # -------------------------

    # Load centralized configuration
    from core.config import get_config
    config = get_config()
    provider_name = (config.model_provider or "mistral").lower()

    if provider_name == "mistral":

        provider = MistralProvider(
            model_name=os.getenv(
                "MISTRAL_MODEL",
                "mistral-small-latest",
            )
        )

    elif provider_name == "qwen":

        provider = QwenProvider(
            model_name=os.getenv(
                "QWEN_MODEL",
                "Qwen/Qwen2.5-0.5B-Instruct",
            ),
            adapter_path="models/checkpoints",
        )

    elif provider_name == "fake":
        # Deterministic fake provider for local testing and portability
        try:
            from models.providers.fake import FakeProvider
            provider = FakeProvider(model_name=os.getenv("FAKE_MODEL", "fake-model"))
        except Exception as exc:
            raise ValueError(f"Failed to initialize fake provider: {exc}") from exc

    else:

        raise ValueError(
            f"Unsupported MODEL_PROVIDER: {provider_name}"
        )

    model_gateway = ModelGateway(
        provider=provider
    )

    # -------------------------
    # RAG
    # -------------------------

    rag = RAGPipeline(enable_inference=provider_name != "fake")

    knowledge_sources = KnowledgeSourceRegistry()

    knowledge_sources.register(
        RAGKnowledgeSource(rag)
    )
    if config.sql_database_path:
        sql_source = SQLKnowledgeSource(
            SQLiteBackend(config.sql_database_path),
            default_query="SELECT * FROM accounts WHERE customer_id = ?",
            aliases=("business db", "sqlite db", "sqlite"),
        )
        sql_source.name = "business_db"
        knowledge_sources.register(sql_source)

    # -------------------------
    # Tools
    # -------------------------

    tool_registry = ToolRegistry()

    tool_registry.register(
        CalculatorTool()
    )

    tool_registry.register(
        StringFormatterTool()
    )

    tool_registry.register(
        TextAnalyzerTool()
    )

    # -------------------------
    # Execution
    # -------------------------

    policy = DefaultPolicy()

    workflows = WorkflowRegistry()
    workflows.register(KnowledgeGroundedAnswerWorkflow())

    # execution_manager is created later after optional components (e.g., knowledge graph) are configured
    # so that optional registries can be injected into it at construction time.

    # -------------------------
    # Planner
    # -------------------------

    planner = Planner(
        model_gateway=model_gateway,
        tool_registry=tool_registry,
        knowledge_source_registry=knowledge_sources,
        workflow_registry=workflows,
    )

    # -------------------------
    # Agent
    # -------------------------

    observer = Observer()

    decision_maker = DecisionMaker()

    context_manager = ContextManager()

    response_synthesizer = ResponseSynthesizer(
        model_gateway=model_gateway
    )

    # Optional persistent memory: configure via PERSISTENT_MEMORY_DB environment variable.
    memory_registry = None
    # Persistent memory DB path from centralized config
    persistent_db = config.persistent_memory_db
    if persistent_db:
        memory_registry = MemoryRegistry()
        db_path = Path(persistent_db)
        # Ensure parent dirs exist
        if not db_path.parent.exists():
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        memory_registry.register(SQLiteMemory(str(db_path)))

    # Optional knowledge graph: controlled by centralized config (backward compatible)
    knowledge_graph_registry = None
    if config.knowledge_graph_enabled or config.neo4j_uri:
        knowledge_graph_registry = KnowledgeGraphRegistry()
        if config.knowledge_graph_enabled:
            knowledge_graph_registry.register(InMemoryKnowledgeGraph())
        if config.neo4j_uri:
            knowledge_graph_registry.register(
                Neo4jKnowledgeGraph(
                    uri=config.neo4j_uri,
                    username=config.neo4j_username or "",
                    password=config.neo4j_password or "",
                    database=config.neo4j_database,
                    name=config.neo4j_graph_name,
                )
            )

    # Create the ExecutionManager after optional components have been configured
    execution_manager = ExecutionManager(
        tool_registry=tool_registry,
        model_gateway=model_gateway,
        knowledge_source_registry=knowledge_sources,
        knowledge_graph_registry=knowledge_graph_registry,
        policy=policy,
    )
    resource_router = ResourceRouter(
        knowledge_source_registry=knowledge_sources,
        knowledge_graph_registry=knowledge_graph_registry,
    )

    # Read max parallel tasks from config; default 1 keeps legacy sequential behavior
    try:
        max_parallel = int(config.max_parallel_tasks)
    except Exception:
        max_parallel = 1

    agent = Agent(
        execution_manager=execution_manager,
        planner=planner,
        observer=observer,
        decision_maker=decision_maker,
        context_manager=context_manager,
        response_synthesizer=response_synthesizer,
        policy=policy,
        workflow_registry=workflows,
        memory_registry=memory_registry,
        knowledge_graph_registry=knowledge_graph_registry,
        max_parallel_tasks=max_parallel,
        resource_router=resource_router,
    )

    # Optional orchestrator: wire an LLM-based delegation planner when autonomous delegation is enabled
    orchestrator = None
    enable_autonomous = config.autonomous_delegation_enabled
    if enable_autonomous:
        try:
            max_delegs = int(config.max_autonomous_delegations)
        except Exception:
            max_delegs = 4
        specialized_registry = SpecializedAgentRegistry()
        # register the default ResearchAgent for discovery (preserve earlier behavior)
        try:
            specialized_registry.register(ResearchAgent(agent))
        except ValueError:
            pass
        # Build an LLM-backed delegation planner that will propose plans in JSON
        delegation_planner = LLMDelegationPlanner(model_gateway=model_gateway, base_planner=DelegationPlanner(specialized_registry), specialized_agent_registry=specialized_registry, max_delegations=max_delegs)
        orchestrator = Orchestrator(agent=agent, workflow_registry=workflows, specialized_agent_registry=specialized_registry, delegation_planner=delegation_planner)
    else:
        orchestrator = Orchestrator(agent=agent, workflow_registry=workflows)

    return agent


def create_orchestrator(
    agent=None,
    workflow_registry=None,
    specialized_agent_registry=None,
):
    """Optional composition helper for the thin orchestrator boundary.

    Existing callers can still use create_agent() directly without any specialized
    agent configuration. If a registry is not supplied, the orchestrator remains
    backward compatible and continues to route only regular Agent and workflow
    requests.
    """
    if agent is None:
        agent = create_agent()

    registry = specialized_agent_registry
    if registry is None:
        registry = SpecializedAgentRegistry()
        try:
            registry.register(ResearchAgent(agent))
        except ValueError:
            pass

    return Orchestrator(
        agent=agent,
        workflow_registry=workflow_registry,
        specialized_agent_registry=registry,
    )
