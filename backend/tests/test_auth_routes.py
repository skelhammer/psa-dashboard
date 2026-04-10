"""Integration tests for auth + admin secrets routes via FastAPI TestClient.

These tests construct a minimal FastAPI app with just the auth and admin
routers, plus the bits of app.state they need. We avoid going through
create_app() because that wires the sync scheduler, which would fire real
HTTP calls during tests.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes_admin_secrets import router as admin_secrets_router
from app.api.routes_auth import router as auth_router
from app.auth.ratelimit import LoginRateLimiter
from app.database import Database
from app.vault import crypto
from app.vault.manager import SecretsManager


@pytest.fixture
async def app(tmp_path: Path) -> FastAPI:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    vault = SecretsManager(db, crypto.generate_kek())

    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key=secrets.token_hex(32),
        session_cookie="psa_test_session",
        max_age=3600,
        same_site="lax",
        https_only=False,
    )
    app.include_router(auth_router)
    app.include_router(admin_secrets_router)

    app.state.db = db
    app.state.vault = vault
    app.state.login_rate_limiter = LoginRateLimiter(
        max_attempts=5, window_seconds=900
    )
    # Stub out the bits hot reload would touch. The hot reload module
    # checks the key prefix and bails out cleanly when no provider is
    # currently active, which is what we want for these tests.
    app.state.providers = {}
    app.state.provider = None

    class _NoopManager:
        engines: dict = {}

    app.state.manager = _NoopManager()

    yield app
    await db.close()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ----- /api/auth/me -----


def test_me_returns_setup_required_when_no_admin(client: TestClient):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["setup_required"] is True
    assert body["authenticated"] is False


# ----- /api/auth/setup -----


def test_setup_creates_admin_and_logs_in(client: TestClient):
    r = client.post(
        "/api/auth/setup", json={"password": "this-is-a-strong-password"}
    )
    assert r.status_code == 201
    assert r.json()["ok"] is True

    # Now me() should report authenticated
    r = client.get("/api/auth/me")
    assert r.json()["authenticated"] is True
    assert r.json()["setup_required"] is False
    assert r.json()["username"] == "admin"


def test_setup_rejects_short_password(client: TestClient):
    r = client.post("/api/auth/setup", json={"password": "short"})
    assert r.status_code == 422  # pydantic validation


def test_setup_blocked_after_admin_exists(client: TestClient):
    client.post("/api/auth/setup", json={"password": "first-strong-password"})
    # Drop the session so we're not authenticated for the second attempt
    client.cookies.clear()
    r = client.post(
        "/api/auth/setup", json={"password": "second-strong-password"}
    )
    assert r.status_code == 403


# ----- /api/auth/login -----


def test_login_with_correct_password_succeeds(client: TestClient):
    client.post(
        "/api/auth/setup", json={"password": "the-correct-password-12345"}
    )
    client.cookies.clear()  # forget the auto-login from setup

    r = client.post(
        "/api/auth/login", json={"password": "the-correct-password-12345"}
    )
    assert r.status_code == 200

    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True


def test_login_with_wrong_password_returns_401(client: TestClient):
    client.post(
        "/api/auth/setup", json={"password": "the-correct-password-12345"}
    )
    client.cookies.clear()

    r = client.post("/api/auth/login", json={"password": "wrong-password-here"})
    assert r.status_code == 401


def test_login_when_no_admin_exists_returns_401(client: TestClient):
    """If no admin has been set up yet, login is universally rejected."""
    r = client.post("/api/auth/login", json={"password": "anything"})
    assert r.status_code == 401


def test_logout_clears_session(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-strong-password-12"})
    assert client.get("/api/auth/me").json()["authenticated"] is True

    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_login_rate_limited_after_5_failures(client: TestClient, app: FastAPI):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})
    client.cookies.clear()
    app.state.login_rate_limiter.reset(None)

    # 5 failed attempts
    for _ in range(5):
        r = client.post("/api/auth/login", json={"password": "wrong-attempt"})
        assert r.status_code == 401

    # 6th is blocked
    r = client.post("/api/auth/login", json={"password": "wrong-attempt"})
    assert r.status_code == 429
    assert "Retry-After" in r.headers


# ----- admin secrets endpoints -----


def test_admin_endpoints_require_auth(client: TestClient):
    r = client.get("/api/admin/secrets")
    assert r.status_code == 401

    r = client.put(
        "/api/admin/secrets/psa.superops.api_token", json={"value": "xyz"}
    )
    assert r.status_code == 401

    r = client.delete("/api/admin/secrets/psa.superops.api_token")
    assert r.status_code == 401

    r = client.get("/api/admin/audit")
    assert r.status_code == 401


def test_list_secrets_returns_all_known_keys_unset(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})
    r = client.get("/api/admin/secrets")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 8  # five secret + three text fields
    keys = {item["key"] for item in body}
    assert "psa.superops.api_token" in keys
    assert "psa.zendesk.api_token" in keys
    assert "psa.zendesk.email" in keys
    assert "psa.superops.subdomain" in keys
    assert "phone.zoom.client_secret" in keys
    for item in body:
        assert item["is_set"] is False
        assert item["value"] is None  # nothing stored, nothing to return


def test_text_field_value_returned_after_set(client: TestClient):
    """Non-secret entries (subdomains, emails) return their stored value
    so the Settings UI can pre-fill the input. Secret entries do not."""
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})

    # Set a non-secret (text) entry
    client.put(
        "/api/admin/secrets/psa.zendesk.email", json={"value": "agent@acme.com"}
    )
    # Set a secret entry
    client.put(
        "/api/admin/secrets/psa.zendesk.api_token", json={"value": "tok-secret-xyz"}
    )

    r = client.get("/api/admin/secrets")
    items = {item["key"]: item for item in r.json()}

    email_item = items["psa.zendesk.email"]
    assert email_item["is_set"] is True
    assert email_item["secret"] is False
    assert email_item["value"] == "agent@acme.com"  # text field IS returned

    token_item = items["psa.zendesk.api_token"]
    assert token_item["is_set"] is True
    assert token_item["secret"] is True
    assert token_item["value"] is None  # secret field NEVER returned


def test_set_secret_then_list_shows_set(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})

    r = client.put(
        "/api/admin/secrets/psa.superops.api_token",
        json={"value": "fresh-token-xyz"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["key"] == "psa.superops.api_token"
    # Reload result reports inactive (the test app has no real providers)
    assert r.json()["reload"]["reloaded"] is False

    r = client.get("/api/admin/secrets")
    superops = next(
        s for s in r.json() if s["key"] == "psa.superops.api_token"
    )
    assert superops["is_set"] is True
    assert superops["updated_at"] is not None


def test_set_secret_unknown_key_returns_404(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})
    r = client.put(
        "/api/admin/secrets/not.a.real.key", json={"value": "anything"}
    )
    assert r.status_code == 404


def test_set_secret_empty_value_rejected(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})
    r = client.put(
        "/api/admin/secrets/psa.superops.api_token", json={"value": ""}
    )
    assert r.status_code == 422  # pydantic min_length


def test_delete_secret_removes_it(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})
    client.put(
        "/api/admin/secrets/psa.zendesk.api_token", json={"value": "abc123"}
    )

    r = client.delete("/api/admin/secrets/psa.zendesk.api_token")
    assert r.status_code == 200

    r = client.get("/api/admin/secrets")
    zendesk = next(s for s in r.json() if s["key"] == "psa.zendesk.api_token")
    assert zendesk["is_set"] is False


def test_delete_missing_secret_returns_404(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})
    r = client.delete("/api/admin/secrets/psa.superops.api_token")
    assert r.status_code == 404


def test_audit_log_shows_set_and_delete_events(client: TestClient):
    client.post("/api/auth/setup", json={"password": "the-correct-password-12"})
    client.put(
        "/api/admin/secrets/psa.superops.api_token", json={"value": "v1"}
    )
    client.delete("/api/admin/secrets/psa.superops.api_token")

    r = client.get("/api/admin/audit")
    assert r.status_code == 200
    body = r.json()
    actions = [e["action"] for e in body]
    assert "delete" in actions
    assert "set" in actions
    # No plaintext value should appear anywhere in the audit response
    raw = r.text
    assert "v1" not in raw
