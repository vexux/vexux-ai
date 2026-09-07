from core.model_gateway.gateway import ModelGateway
from models.providers.qwen import QwenProvider
from agent.planner import Planner
from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool


def main():

    provider = QwenProvider(
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        adapter_path="models/checkpoints",
    )

    gateway = ModelGateway(
        provider=provider
    )

    tool_registry = ToolRegistry()
    tool_registry.register(CalculatorTool())

    planner = Planner(
        model_gateway=gateway,
        tool_registry=tool_registry,
    )

    intent = planner.understand_intent(
        "What is EC2?"
    )

    print("Intent:")
    print(intent)

    plan = planner.create_plan(
        "What is EC2?",
        intent,
    )

    print("\nPlan:")
    print(plan)


if __name__ == "__main__":
    main()