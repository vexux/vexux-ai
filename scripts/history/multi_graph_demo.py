import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.knowledge.multi_graph import execute_multi_graph_request
from apps.fraud.composition import build_fraud_investigation_graphs, create_fraud_investigation_request
from apps.fraud.graph_correlation import correlate_investigation_graph_results


def main() -> None:
    registry = build_fraud_investigation_graphs()
    request = create_fraud_investigation_request(
        "Investigate customer C1001 and identify their associated accounts, fraud cases, and any devices that connect them to other customers."
    )
    result = execute_multi_graph_request(registry, request)
    correlated = correlate_investigation_graph_results(
        result["results"],
        customer_id="C1001",
    )

    print("Customer graph:", registry.get("customer_graph").name)
    print("Fraud graph:", registry.get("fraud_graph").name)
    print("Summary:")
    print(correlated["summary"])
    print("Facts:")
    for fact in correlated["facts"]:
        print(f"- {fact}")


if __name__ == "__main__":
    main()
