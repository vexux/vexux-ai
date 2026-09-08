from core.contracts.capabilities import ModelProviderContract
from core.observability import classify_error, duration_ms, log_event, metrics, timed


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
        start = timed()
        provider_name = self.provider.name
        if callable(provider_name):
            provider_name = provider_name()
        try:
            result = self.provider.generate(prompt, **kwargs)
        except Exception as exc:
            metrics.increment("provider_failures")
            log_event(
                "model.generate.failed",
                provider=provider_name,
                status="failed",
                duration_ms=duration_ms(start),
                error_class=classify_error(exc),
            )
            raise
        log_event(
            "model.generate.completed",
            provider=provider_name,
            status="completed",
            duration_ms=duration_ms(start),
        )
        return result