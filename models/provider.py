from models.loader import ModelLoader


class ModelProvider:

    @staticmethod
    def load(config):

        provider = config["model"]["provider"]

        if provider == "huggingface":
            return ModelLoader.load(config)

        raise ValueError(
            f"Unsupported provider: {provider}"
        )