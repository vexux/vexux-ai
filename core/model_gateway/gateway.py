from core.contracts.capabilities import ModelProviderContract


class ModelGateway:

    def __init__(
        self,
        provider: ModelProviderContract,
    ):

        self.provider = provider

    def generate(
        self,
        prompt: str,
        **kwargs
    ) -> str:

        return self.provider.generate(
            prompt,
            **kwargs,
        )