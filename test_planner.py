from core.model_gateway.gateway import ModelGateway
from models.providers.qwen import QwenProvider
from agent.planner import Planner


def main():

    provider = QwenProvider(
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        adapter_path="models/checkpoints",
    )

    gateway = ModelGateway(
        provider=provider
    )

    planner = Planner(
        model_gateway=gateway
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