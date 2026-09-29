"""JWT token verification and workspace authorization checks."""

from typing import Any
from uuid import UUID

import jwt
import structlog

from rag_core.auth.models import UserIdentity
from rag_core.errors import AuthenticationError, AuthorizationError

logger = structlog.get_logger(__name__)


class SupabaseTokenVerifier:
    """Verifies and decodes Supabase JWT authentication tokens."""

    def __init__(
        self,
        secret_or_public_key: str,
        *,
        audience: str = "authenticated",
        algorithm: str = "HS256",
    ) -> None:
        self._secret = secret_or_public_key
        self._audience = audience
        self._algorithm = algorithm

    def verify(self, token: str) -> UserIdentity:
        """Decode and validate claims in the JWT token."""
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=self._audience,
            )
            raw_sub = payload.get("sub")
            if not raw_sub:
                raise AuthenticationError("JWT missing subject ('sub') claim")

            user_id = UUID(str(raw_sub))
            email = str(payload.get("email", f"{user_id}@user.local"))
            role = str(payload.get("role", "authenticated"))

            app_meta = payload.get("app_metadata", {})
            raw_workspaces = app_meta.get("workspace_ids", [])
            workspace_ids = tuple(UUID(str(w)) for w in raw_workspaces)

            return UserIdentity(
                user_id=user_id,
                email=email,
                roles=(role,),
                workspace_ids=workspace_ids,
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthenticationError("Authentication token has expired") from exc
        except jwt.InvalidTokenError as exc:
            raise AuthenticationError(f"Invalid authentication token: {exc}") from exc
        except Exception as exc:
            logger.error("jwt_verification_failed", error=str(exc))
            raise AuthenticationError("Failed to verify authentication token") from exc


def check_workspace_access(user: UserIdentity, target_workspace_id: UUID) -> None:
    """Ensure the authenticated user is authorized to access the requested workspace."""
    if "service_role" in user.roles or "admin" in user.roles:
        return

    if user.workspace_ids and target_workspace_id not in user.workspace_ids:
        raise AuthorizationError(
            f"User {user.user_id} is not a member of workspace {target_workspace_id}"
        )
