import asyncio

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from api import auth
from api.main import app


def _run_auth(credentials):
    return asyncio.run(auth.get_authenticated_user(credentials))


def test_authentication_rejects_missing_bearer_token():
    with pytest.raises(HTTPException) as error:
        _run_auth(None)

    assert error.value.status_code == 401


def test_authentication_rejects_users_outside_allowlist(monkeypatch):
    monkeypatch.setenv("API_AUTHORIZED_USER_IDS", "allowed-user")

    async def resolve_user_id(_access_token):
        return "different-user"

    monkeypatch.setattr(auth, "_resolve_supabase_user_id", resolve_user_id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    with pytest.raises(HTTPException) as error:
        _run_auth(credentials)

    assert error.value.status_code == 403


def test_authentication_accepts_allowlisted_supabase_user(monkeypatch):
    monkeypatch.setenv("API_AUTHORIZED_USER_IDS", "allowed-user, another-user")

    async def resolve_user_id(_access_token):
        return "allowed-user"

    monkeypatch.setattr(auth, "_resolve_supabase_user_id", resolve_user_id)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")

    assert _run_auth(credentials) == {"id": "allowed-user"}


def test_business_api_requires_bearer_token():
    response = TestClient(app).get("/api/v1/vessels")

    assert response.status_code == 401


def test_health_check_does_not_require_authentication():
    response = TestClient(app).get("/health")

    assert response.status_code == 200
