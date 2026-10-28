"""Trusted actor identities for the local fraud application."""

TRUSTED_ACTORS = frozenset({"investigator", "support_user"})
DEFAULT_ACTOR = "support_user"


def validate_actor(actor: str) -> str:
    """Return an exact trusted actor identifier or reject the identity."""
    if actor not in TRUSTED_ACTORS:
        raise ValueError(
            f"Unknown actor '{actor}'. Use one of: "
            + ", ".join(sorted(TRUSTED_ACTORS))
            + "."
        )
    return actor


__all__ = ["DEFAULT_ACTOR", "TRUSTED_ACTORS", "validate_actor"]
