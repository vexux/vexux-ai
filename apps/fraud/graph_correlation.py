"""Application-specific correlation of registered investigation graph results."""

from __future__ import annotations

from typing import Any, Iterable


def _flatten_graph_items(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        return [result]
    return []


def _extract_identifier(node: Any, identifier_key: str) -> str | None:
    if not isinstance(node, dict):
        return None
    properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    value = properties.get(identifier_key)
    if value is None:
        value = node.get(identifier_key)
    return str(value) if value is not None else None


def correlate_investigation_graph_results(
    results: Iterable[dict[str, Any]],
    customer_id: str | None = None,
) -> dict[str, Any]:
    account_ids: set[str] = set()
    case_ids: set[str] = set()
    device_ids: set[str] = set()
    related_customers: set[str] = set()
    observed_customer_ids: set[str] = set()

    for result in results:
        if not isinstance(result, dict):
            continue
        graph_name = result.get("graph_name") or result.get("source") or "unknown_graph"
        for item in _flatten_graph_items(result.get("result")):
            if isinstance(item.get("node"), dict):
                node = item["node"]
            elif isinstance(item.get("relationship"), dict):
                node = item["relationship"]
            else:
                node = item

            account_id = _extract_identifier(node, "account_id")
            case_id = _extract_identifier(node, "case_id")
            device_id = _extract_identifier(node, "device_id")
            observed_customer_id = _extract_identifier(node, "customer_id")
            if observed_customer_id:
                observed_customer_ids.add(observed_customer_id)
            if account_id:
                account_ids.add(account_id)
            if case_id:
                case_ids.add(case_id)
            if device_id:
                device_ids.add(device_id)
            if observed_customer_id and observed_customer_id != customer_id and customer_id:
                related_customers.add(observed_customer_id)

    if customer_id is None:
        customer_id = next(iter(sorted(observed_customer_ids)), None)

    accounts = sorted(account_ids)
    cases = sorted(case_ids)
    devices = sorted(device_ids)
    other_customers = sorted(related_customers)
    facts: list[str] = []
    if customer_id and accounts:
        facts.append(f"Customer {customer_id} owns accounts {', '.join(accounts)}.")
    if customer_id and cases:
        facts.append(f"The fraud graph associates {customer_id} with case {', '.join(cases)}.")
    if devices:
        if customer_id:
            facts.append(f"Customer {customer_id} is associated with device {', '.join(devices)}.")
        if other_customers:
            facts.append(
                f"Device {', '.join(devices)} is also associated with customer "
                f"{', '.join(other_customers)}."
            )

    return {
        "summary": {
            "customer_id": customer_id,
            "account_ids": accounts,
            "case_ids": cases,
            "device_ids": devices,
            "related_customers": other_customers,
        },
        "facts": facts,
    }


def process_investigation_graph_results(
    task_input: dict[str, Any],
    execution_output: dict[str, Any],
) -> dict[str, Any]:
    return correlate_investigation_graph_results(
        execution_output.get("results", []),
        customer_id=task_input.get("customer_id"),
    )
