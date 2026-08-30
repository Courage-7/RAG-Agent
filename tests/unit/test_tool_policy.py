from datetime import UTC, datetime, timedelta
from uuid import uuid4

from rag_core.tools.models import ApprovalGrant, ToolCallIntent, ToolEffect


def make_intent() -> ToolCallIntent:
    return ToolCallIntent(
        invocation_id=uuid4(),
        workspace_id=uuid4(),
        user_id=uuid4(),
        connector="google_calendar",
        action="create_event",
        effect=ToolEffect.SIDE_EFFECT,
        arguments={"title": "Architecture review", "hour": 14},
        idempotency_key="calendar:create:meeting-123",
    )


def test_approval_is_bound_to_exact_arguments_and_identity() -> None:
    intent = make_intent()
    now = datetime.now(UTC)
    grant = ApprovalGrant(
        approval_id=uuid4(),
        invocation_id=intent.invocation_id,
        workspace_id=intent.workspace_id,
        user_id=intent.user_id,
        arguments_sha256=intent.arguments_sha256,
        expires_at=now + timedelta(minutes=5),
    )

    assert grant.authorizes(intent, at=now)

    changed = intent.model_copy(update={"arguments": {"title": "Different meeting"}})
    assert not grant.authorizes(changed, at=now)


def test_expired_approval_is_rejected() -> None:
    intent = make_intent()
    now = datetime.now(UTC)
    grant = ApprovalGrant(
        approval_id=uuid4(),
        invocation_id=intent.invocation_id,
        workspace_id=intent.workspace_id,
        user_id=intent.user_id,
        arguments_sha256=intent.arguments_sha256,
        expires_at=now - timedelta(seconds=1),
    )

    assert not grant.authorizes(intent, at=now)
