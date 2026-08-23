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

from agent.execution_manager import ExecutionManager
from agent.planner import Planner
from agent.agent import Agent

from agent.observer import Observer
from agent.decision import DecisionMaker
from agent.response_synthesizer import ResponseSynthesizer
from core.memory.registry import MemoryRegistry
from core.memory.sqlite_memory import SQLiteMemory
from pathlib import Path


def create_agent():

    # -------------------------
    # Model
    # -------------------------

    provider_name = os.getenv(
        "MODEL_PROVIDER",
        "mistral",
    ).lower()

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

    rag = RAGPipeline()

    knowledge_sources = KnowledgeSourceRegistry()

    knowledge_sources.register(
        RAGKnowledgeSource(rag)
    )

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

    execution_manager = ExecutionManager(
        tool_registry=tool_registry,
        model_gateway=model_gateway,
        knowledge_source_registry=knowledge_sources,
        policy=policy,
    )

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
    persistent_db = os.getenv("PERSISTENT_MEMORY_DB")
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
    )

    return agent
