"""Command-line entry point for the synthetic fraud investigation demo."""

from __future__ import annotations

import argparse
import os
import sys

from apps.fraud.demo import create_demo_agent


CUSTOMER_IDS = ("C1001", "C1002", "C2001")
_SAFE_DEMO_ENVIRONMENT = {
    "MODEL_PROVIDER": "fake",
    "NEO4J_URI": "",
    "ENABLE_KNOWLEDGE_GRAPH": "0",
    "ENABLE_LOCAL_RAG_INFERENCE": "0",
    "ENABLE_AUTONOMOUS_DELEGATION": "0",
    "PERSISTENT_MEMORY_DB": "",
    "SQL_DATABASE_PATH": "",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Investigate a synthetic fraud-demo customer."
    )
    parser.add_argument("customer_id", choices=CUSTOMER_IDS)
    parser.add_argument(
        "--provider",
        choices=("fake",),
        default="fake",
        help="Use the deterministic fake provider (the only supported demo option).",
    )
    args = parser.parse_args(argv)

    previous_environment = {
        key: os.environ.get(key) for key in _SAFE_DEMO_ENVIRONMENT
    }
    os.environ.update(_SAFE_DEMO_ENVIRONMENT)
    try:
        with create_demo_agent() as agent:
            response = agent.run(
                f"Investigate {args.customer_id}",
                user_id="investigator",
            )
    finally:
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    if response.success:
        print("Status: SUCCESS")
        print(response.output or "No investigation details returned.")
        return 0

    print("Status: FAILURE")
    print(f"Error: {response.error or 'No error details returned.'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
