from core.context.context_manager import ContextManager
from core.contracts.execution import AgentContext
from core.contracts.identity import SecurityContext


def test_security_context_is_preserved_in_request_context():
    identity = SecurityContext(
        actor_id="application-user",
        roles=("reader",),
        claims={"tenant": "tenant-a"},
    )

    context = ContextManager().create(
        request_id="request-1",
        session_id="session-1",
        security_context=identity,
    )

    assert context.security_context is identity
    assert context.user_id is None


def test_legacy_user_id_context_remains_compatible():
    context = ContextManager().create(
        request_id="request-2",
        user_id="legacy-user",
    )

    assert isinstance(context, AgentContext)
    assert context.user_id == "legacy-user"
