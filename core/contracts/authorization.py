from dataclasses import dataclass
from typing import Optional


@dataclass
class AuthorizationRequest:
    actor: Optional[str]
    resource_type: str
    resource_name: Optional[str]
    action: str
    context: Optional[dict] = None

    def __post_init__(self) -> None:
        if self.actor is not None and (
            not isinstance(self.actor, str) or not self.actor.strip()
        ):
            raise ValueError("actor must be a non-empty string when provided.")
        if not isinstance(self.resource_type, str) or not self.resource_type.strip():
            raise ValueError("resource_type must be a non-empty string.")
        if self.resource_name is not None and (
            not isinstance(self.resource_name, str) or not self.resource_name.strip()
        ):
            raise ValueError("resource_name must be a non-empty string when provided.")
        if not isinstance(self.action, str) or not self.action.strip():
            raise ValueError("action must be a non-empty string.")
        if self.context is not None and not isinstance(self.context, dict):
            raise ValueError("context must be a dictionary when provided.")


@dataclass
class AuthorizationDecision:
    allowed: bool
    reason: Optional[str] = None
    policy_name: str = "authorization"
