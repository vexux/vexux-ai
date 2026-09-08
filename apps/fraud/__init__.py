"""Fraud application boundary for domain-specific fixtures, policies, and composition."""

from apps.fraud.composition import (
    build_fraud_investigation_graphs,
    create_customer_fraud_graphs,
    create_fraud_investigation_fixture,
    create_fraud_investigation_request,
)
from apps.fraud.demo import DemoPolicy, create_demo_agent
from apps.fraud.policy import FraudPolicy
from apps.fraud.real import create_real_agent

__all__ = [
    "DemoPolicy",
    "FraudPolicy",
    "create_real_agent",
    "build_fraud_investigation_graphs",
    "create_customer_fraud_graphs",
    "create_demo_agent",
    "create_fraud_investigation_fixture",
    "create_fraud_investigation_request",
]
