"""Fraud investigation domain entities and result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.contracts.evidence import EvidenceSet


def _required(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


@dataclass(frozen=True)
class Customer:
    customer_id: str
    name: str | None = None
    risk_level: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "customer_id", _required(self.customer_id, "customer_id"))


@dataclass(frozen=True)
class Account:
    account_id: str
    customer_id: str
    status: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "account_id", _required(self.account_id, "account_id"))
        object.__setattr__(self, "customer_id", _required(self.customer_id, "customer_id"))


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    customer_id: str
    amount: float
    status: str
    account_id: str | None = None
    merchant_id: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "transaction_id", _required(self.transaction_id, "transaction_id"))
        object.__setattr__(self, "customer_id", _required(self.customer_id, "customer_id"))
        if self.amount < 0:
            raise ValueError("amount must not be negative.")


@dataclass(frozen=True)
class Merchant:
    merchant_id: str
    name: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "merchant_id", _required(self.merchant_id, "merchant_id"))


@dataclass(frozen=True)
class Device:
    device_id: str

    def __post_init__(self):
        object.__setattr__(self, "device_id", _required(self.device_id, "device_id"))


@dataclass(frozen=True)
class Address:
    address_id: str

    def __post_init__(self):
        object.__setattr__(self, "address_id", _required(self.address_id, "address_id"))


@dataclass(frozen=True)
class FraudAlert:
    alert_id: str
    customer_id: str
    alert_type: str
    severity: str
    status: str

    def __post_init__(self):
        object.__setattr__(self, "alert_id", _required(self.alert_id, "alert_id"))
        object.__setattr__(self, "customer_id", _required(self.customer_id, "customer_id"))


@dataclass(frozen=True)
class FraudCase:
    fraud_case_id: str
    customer_id: str
    status: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "fraud_case_id", _required(self.fraud_case_id, "fraud_case_id"))
        object.__setattr__(self, "customer_id", _required(self.customer_id, "customer_id"))


@dataclass(frozen=True)
class Investigation:
    investigation_id: str
    customer_id: str
    fraud_case_id: str
    status: str

    def __post_init__(self):
        object.__setattr__(self, "investigation_id", _required(self.investigation_id, "investigation_id"))
        object.__setattr__(self, "customer_id", _required(self.customer_id, "customer_id"))


@dataclass(frozen=True)
class InvestigationEvent:
    event_type: str
    payload: Any
    investigation_id: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "event_type", _required(self.event_type, "event_type"))


@dataclass
class InvestigationResult:
    subject: Customer
    findings: list[str] = field(default_factory=list)
    risk_assessment: str = "low"
    supporting_evidence: EvidenceSet = field(default_factory=EvidenceSet)
    contributing_signals: list[str] = field(default_factory=list)
    resources_consulted: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.risk_assessment not in {"low", "medium", "high"}:
            raise ValueError("risk_assessment must be low, medium, or high.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject": {
                "customer_id": self.subject.customer_id,
                "name": self.subject.name,
                "risk_level": self.subject.risk_level,
            },
            "findings": list(self.findings),
            "risk_assessment": self.risk_assessment,
            "contributing_signals": list(self.contributing_signals),
            "resources_consulted": list(self.resources_consulted),
            "metadata": dict(self.metadata),
            "evidence": [
                {
                    "source": item.source,
                    "content": item.content,
                    "evidence_type": item.evidence_type,
                    "metadata": dict(item.metadata),
                }
                for item in self.supporting_evidence.items
            ],
        }
