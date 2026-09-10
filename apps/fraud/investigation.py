"""Deterministic fraud investigation service."""

from __future__ import annotations

from typing import Any

from core.contracts.evidence import Evidence, EvidenceSet

from apps.fraud.domain import (
    Customer,
    FraudAlert,
    Investigation,
    InvestigationResult,
    Transaction,
)


class FraudInvestigationService:
    """Gather and correlate fraud facts through injected generic resources."""

    def __init__(self, graph_registry, source_registry, policy):
        self.graph_registry = graph_registry
        self.source_registry = source_registry
        self.policy = policy

    def _authorize(self, actor: str, resource_type: str, resource_name: str) -> None:
        decision = self.policy.authorize_resource(actor, resource_type, resource_name, "read")
        if not decision.allowed:
            raise PermissionError(f"Unauthorized access to {resource_type}: {resource_name}")

    @staticmethod
    def _add_graph_evidence(evidence: EvidenceSet, source: str, value: Any, kind: str) -> None:
        evidence.add(Evidence(source, str(value), kind))

    def build_result(
        self,
        customer_node: dict[str, Any],
        fraud_neighbors: list[dict[str, Any]],
        transaction_rows: list[dict[str, Any]],
        alert_rows: list[dict[str, Any]],
        investigation_rows: list[dict[str, Any]],
        evidence: EvidenceSet | None = None,
        resources_consulted: list[str] | None = None,
    ) -> InvestigationResult:
        """Correlate already-authorized observations without performing I/O."""
        properties = customer_node.get("properties", {})
        customer_id = customer_node.get("id")
        if not isinstance(customer_id, str) or not customer_id.strip():
            raise ValueError("customer_node must contain a non-empty id.")
        subject = Customer(customer_id, properties.get("name"), properties.get("risk"))
        evidence = evidence or EvidenceSet()
        transactions = [
            Transaction(
                transaction_id=row["transaction_id"],
                customer_id=row["customer_id"],
                amount=float(row["amount"]),
                status=row["status"],
                account_id=row.get("account_id"),
                merchant_id=row.get("merchant_id"),
            )
            for row in transaction_rows
        ]
        alerts = [
            FraudAlert(
                alert_id=row["alert_id"],
                customer_id=row["customer_id"],
                alert_type=row["alert_type"],
                severity=row["severity"],
                status=row["status"],
            )
            for row in alert_rows
        ]
        investigations = [
            Investigation(
                investigation_id=row["investigation_id"],
                customer_id=row["customer_id"],
                fraud_case_id=row["fraud_case_id"],
                status=row["status"],
            )
            for row in investigation_rows
        ]
        findings: list[str] = []
        signals: list[str] = []
        high_alerts = [alert for alert in alerts if alert.severity == "high" and alert.status == "open"]
        if high_alerts:
            signals.append("open_high_severity_alerts")
            findings.append(f"{len(high_alerts)} open high-severity fraud alert(s) are associated with the customer.")
        if len(transactions) >= 2 and sum(transaction.amount for transaction in transactions) > 2000:
            signals.append("elevated_transaction_activity")
            findings.append("Transaction activity exceeds the deterministic investigation threshold.")
        shared_device = any(
            str(item.get("relationship", {}).get("type", "")).upper()
            in {"SHARES_DEVICE_WITH", "SHARED_DEVICE", "LINKED_TO"}
            for item in fraud_neighbors
            if item.get("relationship")
        )
        if shared_device:
            signals.append("shared_device_relationship")
            findings.append("The customer is connected to another customer through a shared device.")
        if investigations:
            signals.append("active_investigation")
            findings.append("An investigation record is associated with the customer.")
        risk = "high" if len(signals) >= 2 or high_alerts else "medium" if signals else "low"
        return InvestigationResult(
            subject=subject,
            findings=findings,
            risk_assessment=risk,
            supporting_evidence=evidence,
            contributing_signals=signals,
            resources_consulted=list(dict.fromkeys(resources_consulted or [])),
            metadata={
                "transaction_count": len(transactions),
                "alert_count": len(alerts),
                "investigation_count": len(investigations),
            },
        )

    def investigate(self, customer_id: str, actor: str = "investigator") -> InvestigationResult:
        if not isinstance(customer_id, str) or not customer_id.strip():
            raise ValueError("customer_id must be a non-empty string.")
        customer_id = customer_id.strip()
        evidence = EvidenceSet()
        consulted: list[str] = []

        # Authorize every protected resource before performing any I/O.
        for resource_type, resource_name in (
            ("knowledge_graph", "customer_graph"),
            ("knowledge_graph", "fraud_graph"),
            ("knowledge_source", "business_db"),
        ):
            self._authorize(actor, resource_type, resource_name)

        customer_graph = self.graph_registry.get("customer_graph")
        customer_node = customer_graph.get_node(customer_id)
        consulted.append("customer_graph")
        self._add_graph_evidence(evidence, "customer_graph", customer_node, "graph_node")
        customer_neighbors = customer_graph.get_neighbors(customer_id, direction="both")
        for item in customer_neighbors:
            self._add_graph_evidence(evidence, "customer_graph", item, "graph_relationship")

        fraud_graph = self.graph_registry.get("fraud_graph")
        fraud_neighbors = fraud_graph.get_neighbors(customer_id, direction="both")
        consulted.append("fraud_graph")
        for item in fraud_neighbors:
            self._add_graph_evidence(evidence, "fraud_graph", item, "graph_relationship")

        business_db = self.source_registry.get("business_db")
        transaction_rows = business_db.retrieve(
            "SELECT transaction_id, account_id, customer_id, merchant_id, amount, currency, occurred_at, status "
            "FROM transactions WHERE customer_id = %s ORDER BY occurred_at",
            parameters=(customer_id,),
        )
        alert_rows = business_db.retrieve(
            "SELECT alert_id, customer_id, transaction_id, alert_type, severity, status "
            "FROM fraud_alerts WHERE customer_id = %s ORDER BY created_at",
            parameters=(customer_id,),
        )
        investigation_rows = business_db.retrieve(
            "SELECT investigation_id, customer_id, fraud_case_id, status "
            "FROM investigations WHERE customer_id = %s ORDER BY opened_at",
            parameters=(customer_id,),
        )
        consulted.append("business_db")
        for row in transaction_rows + alert_rows + investigation_rows:
            self._add_graph_evidence(evidence, "business_db", row, "structured_data")

        return self.build_result(
            customer_node,
            fraud_neighbors,
            transaction_rows,
            alert_rows,
            investigation_rows,
            evidence=evidence,
            resources_consulted=consulted,
        )
