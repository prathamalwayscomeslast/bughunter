from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orchestrator.schemas.auth import AuthenticatedUser
from orchestrator.security.firebase import (
    FirebaseTokenVerificationError,
    extract_identity,
    verify_firebase_token,
)

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Authentication required.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer_scheme),
        ],
) -> AuthenticatedUser:
    """
    Validate Authorization: Bearer <firebase_id_token>
    and return a normalized authenticated user object.
    """
    if credentials is None:
        raise _unauthorized("Missing bearer token.")

    if credentials.scheme.lower() != "bearer":
        raise _unauthorized("Invalid authentication scheme.")

    token = credentials.credentials
    if not token or not token.strip():
        raise _unauthorized("Missing bearer token.")

    try:
        decoded_token = verify_firebase_token(token)
        identity = extract_identity(decoded_token)
    except FirebaseTokenVerificationError as exc:
        raise _unauthorized(str(exc)) from exc

    uid = identity.get("uid")
    if not uid:
        raise _unauthorized("Token is valid but missing user identity.")

    return AuthenticatedUser(
        firebase_uid=uid,
        email=identity.get("email"),
        email_verified=identity.get("email_verified", False),
        display_name=identity.get("name"),
        photo_url=identity.get("picture"),
        sign_in_provider=identity.get("sign_in_provider"),
        issuer=identity.get("issuer"),
        audience=identity.get("audience"),
    )


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]