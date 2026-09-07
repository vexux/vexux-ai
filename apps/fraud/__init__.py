"""Fraud application boundary for domain-specific fixtures, policies, and composition."""

from apps.fraud.composition import (
    build_fraud_investigation_graphs,
    create_customer_fraud_graphs,
    create_fraud_investigation_fixture,
    create_fraud_investigation_request,
)
from apps.fraud.policy import FraudPolicy

__all__ = [
    "FraudPolicy",
    "build_fraud_investigation_graphs",
    "create_customer_fraud_graphs",
    "create_fraud_investigation_fixture",
    "create_fraud_investigation_request",
]
