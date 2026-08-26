from dataclasses import dataclass
from typing import Optional


@dataclass
class AuthorizationRequest:
    actor: Optional[str]
    resource_type: str
    resource_name: Optional[str]
    action: str
    context: Optional[dict] = None


@dataclass
class AuthorizationDecision:
    allowed: bool
    reason: Optional[str] = None
    policy_name: str = "authorization"
