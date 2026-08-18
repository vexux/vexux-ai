from rag.pipeline import RAGPipeline

from core.model_gateway.gateway import ModelGateway
from models.providers.qwen import QwenProvider

from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool
from core.tools.string_formatter import StringFormatterTool
from core.tools.text_analyzer import TextAnalyzerTool
from core.context.context_manager import ContextManager

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

    provider = QwenProvider(
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        adapter_path="models/checkpoints",
    )

    model_gateway = ModelGateway(
        provider=provider
    )

    # -------------------------
    # RAG
    # -------------------------

    rag = RAGPipeline()

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
        retrieval=rag,
        tool_registry=tool_registry,
        model_gateway=model_gateway,
    )

    # -------------------------
    # Planner
    # -------------------------

    planner = Planner(
        model_gateway=model_gateway
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