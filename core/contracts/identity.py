"""Generic authenticated identity context passed through agent execution."""

from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Tuple


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class SecurityContext:
    """Application-supplied identity and claims; authentication stays outside core."""

    actor_id: str | None = None
    roles: Tuple[str, ...] = ()
    claims: Mapping[str, Any] = field(default_factory=dict)
    attributes: Mapping[str, Any] = field(default_factory=dict)
    authentication_method: str | None = None

    def __post_init__(self) -> None:
        if self.actor_id is not None and (
            not isinstance(self.actor_id, str) or not self.actor_id.strip()
        ):
            raise ValueError("actor_id must be a non-empty string when provided.")
        if not isinstance(self.roles, tuple) or any(
            not isinstance(role, str) or not role.strip() for role in self.roles
        ):
            raise ValueError("roles must be a tuple of non-empty strings.")
        if not isinstance(self.claims, Mapping) or not isinstance(self.attributes, Mapping):
            raise ValueError("claims and attributes must be mappings.")
        object.__setattr__(
            self,
            "claims",
            _freeze(deepcopy(dict(self.claims))),
        )
        object.__setattr__(
            self,
            "attributes",
            _freeze(deepcopy(dict(self.attributes))),
        )
