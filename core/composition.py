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

from agent.execution_manager import ExecutionManager
from agent.planner import Planner
from agent.agent import Agent

from agent.observer import Observer
from agent.decision import DecisionMaker
from agent.response_synthesizer import ResponseSynthesizer


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

    execution_manager = ExecutionManager(
        tool_registry=tool_registry,
        model_gateway=model_gateway,
        knowledge_source_registry=knowledge_sources,
    )

    # -------------------------
    # Planner
    # -------------------------

    planner = Planner(
        model_gateway=model_gateway,
        tool_registry=tool_registry,
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

    agent = Agent(
        execution_manager=execution_manager,
        planner=planner,
        observer=observer,
        decision_maker=decision_maker,
        context_manager=context_manager,
        response_synthesizer=response_synthesizer,
    )

    return agent
