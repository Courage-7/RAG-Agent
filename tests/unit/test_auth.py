import time
from uuid import uuid4

import jwt
import pytest
from rag_core.auth.models import UserIdentity
from rag_core.auth.tokens import SupabaseTokenVerifier, check_workspace_access
from rag_core.errors import AuthenticationError, AuthorizationError

SECRET = "super-secret-test-key-32-chars-long"


def test_verifier_decodes_valid_jwt() -> None:
    verifier = SupabaseTokenVerifier(secret_or_public_key=SECRET)
    user_id = uuid4()
    ws_id = uuid4()

    token = jwt.encode(
        {
            "sub": str(user_id),
            "email": "engineer@company.com",
            "role": "authenticated",
            "aud": "authenticated",
            "exp": time.time() + 3600,
            "app_metadata": {"workspace_ids": [str(ws_id)]},
        },
        SECRET,
        algorithm="HS256",
    )

    identity = verifier.verify(token)

    assert identity.user_id == user_id
    assert identity.email == "engineer@company.com"
    assert identity.roles == ("authenticated",)
    assert identity.workspace_ids == (ws_id,)


def test_verifier_rejects_expired_jwt() -> None:
    verifier = SupabaseTokenVerifier(secret_or_public_key=SECRET)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "aud": "authenticated",
            "exp": time.time() - 100,  # expired
        },
        SECRET,
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError, match="expired"):
        verifier.verify(token)


def test_verifier_rejects_invalid_signature() -> None:
    verifier = SupabaseTokenVerifier(secret_or_public_key=SECRET)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "aud": "authenticated",
            "exp": time.time() + 3600,
        },
        "wrong-secret-key-that-is-32-chars-long",
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError, match="Invalid authentication token"):
        verifier.verify(token)


def test_check_workspace_access_allows_member() -> None:
    user_id = uuid4()
    ws_id = uuid4()
    user = UserIdentity(
        user_id=user_id,
        email="user@test.com",
        workspace_ids=(ws_id,),
    )
    # Should not raise
    check_workspace_access(user, ws_id)


def test_check_workspace_access_blocks_non_member() -> None:
    user_id = uuid4()
    ws_id1 = uuid4()
    ws_id2 = uuid4()
    user = UserIdentity(
        user_id=user_id,
        email="user@test.com",
        workspace_ids=(ws_id1,),
    )
    with pytest.raises(AuthorizationError, match="not a member"):
        check_workspace_access(user, ws_id2)


def test_check_workspace_access_allows_admin() -> None:
    user_id = uuid4()
    arbitrary_ws = uuid4()
    user = UserIdentity(
        user_id=user_id,
        email="admin@test.com",
        roles=("service_role",),
        workspace_ids=(),
    )
    # Service role bypasses workspace restriction
    check_workspace_access(user, arbitrary_ws)
