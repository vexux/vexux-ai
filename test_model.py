from core.model_gateway.gateway import ModelGateway
from models.providers.qwen import QwenProvider


def main():

    provider = QwenProvider(
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        adapter_path="models/checkpoints",
    )

    gateway = ModelGateway(
        provider=provider
    )

    print("Provider:", provider.name)

    answer = gateway.generate(
        "What is EC2?"
    )

    print("\nAnswer:")
    print(answer)


if __name__ == "__main__":
    main()