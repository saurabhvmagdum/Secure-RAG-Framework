"""
Authentication Middleware
=========================

FastAPI middleware for JWT-based internal authentication.
Extracts principal from JWT token, validates, and attaches to request state.

Phase 1: Internal JWT auth.
Future: LDAP/AD integration via auth provider abstraction.

Fail-closed: missing or invalid tokens result in 401.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.core.correlation import get_correlation_id
from app.core.logging import get_logger
from app.models.auth import Principal, PrincipalType

logger = get_logger(__name__)

# FastAPI security scheme for JWT bearer tokens
_bearer_scheme = HTTPBearer(auto_error=True)


@runtime_checkable
class AuthProvider(Protocol):
    """
    Protocol for authentication providers.

    Phase 1 implementation: JWT-based internal auth.
    Phase N: LDAP/AD provider implementing the same interface.
    """

    def validate_token(self, token: str) -> Principal:
        """
        Validate an authentication token and return the Principal.

        Raises:
            AuthenticationError if token is invalid or expired.
        """
        ...

    def create_token(self, principal: Principal) -> str:
        """Create a signed authentication token for a principal."""
        ...


class JWTAuthProvider:
    """
    JWT-based authentication provider for Phase 1.

    Uses python-jose for JWT operations. Keys stored on-prem only.
    """

    def __init__(
        self,
        secret_key: str | None = None,
        algorithm: str | None = None,
        expiration_minutes: int | None = None,
    ) -> None:
        self._secret_key = secret_key or settings.security.jwt_secret_key
        self._algorithm = algorithm or settings.security.jwt_algorithm
        self._expiration_minutes = (
            expiration_minutes or settings.security.jwt_expiration_minutes
        )

    def validate_token(self, token: str) -> Principal:
        """Validate JWT and extract principal. Fail-closed on any error."""
        try:
            from jose import JWTError, jwt

            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )

            principal_id = payload.get("sub")
            if not principal_id:
                raise ValueError("Token missing 'sub' claim")

            return Principal(
                principal_id=principal_id,
                type=PrincipalType(payload.get("type", "USER")),
                display_name=payload.get("name", ""),
                roles=payload.get("roles", []),
            )

        except Exception as exc:
            logger.warning(
                "auth_token_invalid",
                error=str(exc),
                correlation_id=get_correlation_id(),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    def create_token(self, principal: Principal) -> str:
        """Create a signed JWT for the given principal."""
        from jose import jwt

        now = datetime.now(tz=timezone.utc)
        payload = {
            "sub": principal.principal_id,
            "type": principal.type.value,
            "name": principal.display_name,
            "roles": principal.roles,
            "iat": now,
            "exp": now + timedelta(minutes=self._expiration_minutes),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)


# ── Module-level auth provider instance ─────────────────────────────────────
_auth_provider: AuthProvider | None = None


def get_auth_provider() -> AuthProvider:
    """Get the configured auth provider (singleton)."""
    global _auth_provider
    if _auth_provider is None:
        _auth_provider = JWTAuthProvider()
    return _auth_provider


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> Principal:
    """
    FastAPI dependency: extract and validate the current principal from
    the Authorization header.

    Usage in route:
        @router.get("/query")
        async def query(principal: Principal = Depends(get_current_principal)):
            ...
    """
    provider = get_auth_provider()
    return provider.validate_token(credentials.credentials)
