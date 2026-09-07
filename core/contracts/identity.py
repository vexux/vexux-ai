"""Generic authenticated identity context passed through agent execution."""

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class SecurityContext:
    """Application-supplied identity and claims; authentication stays outside core."""

    actor_id: str | None = None
    roles: Tuple[str, ...] = ()
    claims: Dict[str, Any] = field(default_factory=dict)
    attributes: Dict[str, Any] = field(default_factory=dict)
    authentication_method: str | None = None
