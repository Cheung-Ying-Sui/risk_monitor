from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _supabase_service_key() -> str | None:
    return (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )


async def _resolve_supabase_user(access_token: str) -> tuple[str, str | None, bool]:
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
    created_at = user.get("created_at") if isinstance(user, dict) else None
    return (
        user_id,
        created_at if isinstance(created_at, str) else None,
        user.get("is_anonymous") is True,
    )


async def get_authenticated_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    request: Request,
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
    public_signup_access = os.getenv("API_PUBLIC_SIGNUP_ACCESS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    public_guest_write_access = os.getenv("API_PUBLIC_GUEST_WRITE_ACCESS", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not allowed_user_ids and not public_signup_access and not public_guest_write_access:
        logger.error("API_AUTHORIZED_USER_IDS is not configured.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API access is not configured.",
        )

    user_id, created_at, is_anonymous = await _resolve_supabase_user(credentials.credentials)
    if user_id in allowed_user_ids:
        return {"id": user_id, "is_temporary": False}

    if is_anonymous and public_guest_write_access:
        return {"id": user_id, "is_temporary": False, "is_anonymous": True}

    if not public_signup_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not authorized to access the platform.",
        )

    try:
        access_days = int(os.getenv("API_TEMP_USER_ACCESS_DAYS", "7"))
        if access_days < 1:
            raise ValueError
    except ValueError as exc:
        logger.error("API_TEMP_USER_ACCESS_DAYS must be a positive integer.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Temporary account access is not configured.",
        ) from exc

    try:
        if not created_at:
            raise ValueError
        account_created_at = datetime.fromisoformat(
            created_at.replace("Z", "+00:00"),
        )
        if account_created_at.tzinfo is None:
            raise ValueError
        account_created_at = account_created_at.astimezone(timezone.utc)
    except ValueError as exc:
        logger.error("Supabase authentication response did not contain a valid creation time.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service returned an invalid user.",
        ) from exc

    expires_at = account_created_at + timedelta(days=access_days)
    if datetime.now(timezone.utc) >= expires_at:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Temporary account access has expired.",
        )

    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Temporary accounts have read-only access.",
        )

    return {
        "id": user_id,
        "is_temporary": True,
        "expires_at": expires_at.isoformat(),
    }
