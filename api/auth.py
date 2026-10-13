from __future__ import annotations

import logging
import os
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _supabase_service_key() -> str | None:
    return (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )


async def _resolve_supabase_user_id(access_token: str) -> str:
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = _supabase_service_key()
    if not supabase_url or not service_key:
        logger.error("Supabase authentication is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is not configured.",
        )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {access_token}",
                },
            )
    except httpx.RequestError as exc:
        logger.warning("Supabase authentication request failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        ) from exc

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if response.status_code != 200:
        logger.error("Supabase authentication returned HTTP %s.", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service returned an unexpected response.",
        )

    try:
        user = response.json()
    except ValueError as exc:
        logger.error("Supabase authentication returned invalid JSON.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service returned an invalid response.",
        ) from exc

    user_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(user_id, str) or not user_id:
        logger.error("Supabase authentication response did not contain a user ID.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service returned an invalid user.",
        )
    return user_id


async def get_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    allowed_user_ids = {
        user_id.strip()
        for user_id in os.getenv("API_AUTHORIZED_USER_IDS", "").split(",")
        if user_id.strip()
    }
    if not allowed_user_ids:
        logger.error("API_AUTHORIZED_USER_IDS is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API access is not configured.",
        )

    user_id = await _resolve_supabase_user_id(credentials.credentials)
    if user_id not in allowed_user_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not authorized to access the platform.",
        )
    return {"id": user_id}
