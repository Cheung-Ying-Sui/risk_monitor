import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from starlette.requests import Request

from api import auth
from api.main import app


def _run_auth(credentials, method="GET"):
    request = Request({"type": "http", "method": method, "headers": []})
    return asyncio.run(auth.get_authenticated_user(credentials, request))


def test_authentication_rejects_missing_bearer_token():
    with pytest.raises(HTTPException) as error:
        _run_auth(None)

    assert error.value.status_code == 401


def test_authentication_rejects_users_outside_allowlist(monkeypatch):
    monkeypatch.setenv("API_AUTHORIZED_USER_IDS", "allowed-user")

    async def resolve_user(_access_token):
        return "different-user", None

    monkeypatch.setattr(auth, "_resolve_supabase_user", resolve_user)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    with pytest.raises(HTTPException) as error:
        _run_auth(credentials)

    assert error.value.status_code == 403


def test_authentication_accepts_allowlisted_supabase_user(monkeypatch):
    monkeypatch.setenv("API_AUTHORIZED_USER_IDS", "allowed-user, another-user")

    async def resolve_user(_access_token):
        return "allowed-user", None

    monkeypatch.setattr(auth, "_resolve_supabase_user", resolve_user)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    assert _run_auth(credentials) == {"id": "allowed-user", "is_temporary": False}


def test_temporary_signup_account_can_read_within_seven_days(monkeypatch):
    monkeypatch.setenv("API_AUTHORIZED_USER_IDS", "existing-user")
    monkeypatch.setenv("API_PUBLIC_SIGNUP_ACCESS", "true")
    monkeypatch.setenv("API_TEMP_USER_ACCESS_DAYS", "7")
    created_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    async def resolve_user(_access_token):
        return "new-user", created_at

    monkeypatch.setattr(auth, "_resolve_supabase_user", resolve_user)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    result = _run_auth(credentials)

    assert result["id"] == "new-user"
    assert result["is_temporary"] is True
    assert result["expires_at"]


def test_temporary_signup_account_cannot_write(monkeypatch):
    monkeypatch.setenv("API_AUTHORIZED_USER_IDS", "existing-user")
    monkeypatch.setenv("API_PUBLIC_SIGNUP_ACCESS", "true")
    created_at = datetime.now(timezone.utc).isoformat()

    async def resolve_user(_access_token):
        return "new-user", created_at

    monkeypatch.setattr(auth, "_resolve_supabase_user", resolve_user)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    with pytest.raises(HTTPException) as error:
        _run_auth(credentials, method="POST")

    assert error.value.status_code == 403
    assert error.value.detail == "Temporary accounts have read-only access."


def test_temporary_signup_account_expires_after_seven_days(monkeypatch):
    monkeypatch.setenv("API_AUTHORIZED_USER_IDS", "existing-user")
    monkeypatch.setenv("API_PUBLIC_SIGNUP_ACCESS", "true")
    created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()

    async def resolve_user(_access_token):
        return "new-user", created_at

    monkeypatch.setattr(auth, "_resolve_supabase_user", resolve_user)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    with pytest.raises(HTTPException) as error:
        _run_auth(credentials)

    assert error.value.status_code == 403
    assert error.value.detail == "Temporary account access has expired."


def test_business_api_requires_bearer_token():
    response = TestClient(app).get("/api/v1/vessels")

    assert response.status_code == 401


def test_health_check_does_not_require_authentication():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
