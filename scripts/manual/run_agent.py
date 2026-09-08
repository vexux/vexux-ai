"""Interactive runner for the real local fraud application."""

import logging

from apps.fraud.real import create_real_agent
from core.config import get_config


LOGGER = logging.getLogger(__name__)


def _provider_error_message(error: RuntimeError) -> str:
    """Return a concise interactive message for a provider failure."""
    details = []
    current = error
    while current is not None:
        details.append(str(current).lower())
        current = current.__cause__ or current.__context__

    if any(
        marker in " ".join(details)
        for marker in ("429", "rate limit", "rate_limited", "too many requests")
    ):
        return (
            f"The configured model provider '{get_config().model_provider}' "
            "is temporarily unavailable or rate limited. Please try again later."
        )

    return (
        f"The configured model provider '{get_config().model_provider}' "
        "could not complete the request."
    )


def main():
    agent = create_real_agent()
    actor = "investigator"
    session_id = "terminal-session"

    print("=" * 60)
    print("Vexux AI Interactive Terminal")
    print("Type 'exit' or 'quit' to stop. Use '/actor investigator' or '/actor support_user'.")
    print("Resource-aware fraud queries use the real Neo4j and MySQL resources.")
    print("=" * 60)

    while True:
        query = input("\nYou: ").strip()

        if query.lower() in {"exit", "quit"}:
            print("Exiting...")
            break

        if query.lower().startswith("/actor "):
            actor = query.split(None, 1)[1].strip()
            print(f"Actor: {actor}")
            continue

        if not query:
            continue

        try:
            route = agent.resource_router.route(query)
            print("\nDetected resources:")
            for selection in route.selections if route else []:
                print(f"- {selection.name}")
        except ValueError as exc:
            print(f"\nRouting error: {exc}")

        try:
            result = agent.run(query, session_id=session_id, user_id=actor)
        except RuntimeError as exc:
            LOGGER.error("Interactive model provider request failed.", exc_info=exc)
            print(f"\nError: {_provider_error_message(exc)}")
            continue

        print("\nAgent:")
        print(result.output)

        if result.error:
            print("\nError:")
            print(result.error)

        sources_used = {
            item.source
            for observation in result.trace
            for evidence in (
                [observation.output.get("evidence")]
                if isinstance(observation.output, dict)
                else []
            )
            if evidence is not None
            for item in getattr(evidence, "items", [])
        }
        if sources_used:
            print("Sources:", sorted(sources_used))
        print("\nSuccess:", result.success)
        print("Trace length:", len(result.trace))


if __name__ == "__main__":
    main()
