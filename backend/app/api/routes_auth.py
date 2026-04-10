"""Auth endpoints: setup, login, logout, current user."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    hash_password,
    verify_password,
)
from app.auth.users import (
    any_admin_exists,
    create_admin_user,
    get_admin_user,
    update_last_login,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupRequest(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    password: str


class MeResponse(BaseModel):
    authenticated: bool
    setup_required: bool
    username: str | None = None


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate limiting."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _set_session(request: Request, username: str) -> None:
    request.session["user"] = {"username": username, "role": "admin"}


@router.get("/me", response_model=MeResponse)
async def get_me(request: Request) -> MeResponse:
    """Tell the frontend the current auth state.

    Three possible states:
    - setup_required=True: no admin exists yet, frontend should show "set
      initial password" form.
    - authenticated=False: admin exists but no valid session, frontend
      should show login form.
    - authenticated=True: session is valid, frontend can render Settings.
    """
    db = request.app.state.db
    has_admin = await any_admin_exists(db)
    if not has_admin:
        return MeResponse(authenticated=False, setup_required=True)

    user = (request.session or {}).get("user")
    if not user:
        return MeResponse(authenticated=False, setup_required=False)
    return MeResponse(
        authenticated=True,
        setup_required=False,
        username=user.get("username", "admin"),
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def setup_admin(payload: SetupRequest, request: Request) -> dict:
    """Create the initial admin user. Allowed exactly once.

    After this endpoint succeeds, subsequent calls return 403 Forbidden.
    The created user is automatically logged in (session cookie set).
    """
    db = request.app.state.db
    if await any_admin_exists(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin user already exists; use /api/auth/login",
        )
    try:
        pw_hash = hash_password(payload.password)
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    user = await create_admin_user(db, "admin", pw_hash)
    _set_session(request, user.username)
    logger.info("auth: initial admin user created from %s", _client_ip(request))
    return {"ok": True, "username": user.username}


@router.post("/login")
async def login(payload: LoginRequest, request: Request) -> dict:
    """Authenticate against the admin password and start a session."""
    db = request.app.state.db
    rate_limiter = request.app.state.login_rate_limiter
    ip = _client_ip(request)

    if not rate_limiter.check(ip):
        retry = rate_limiter.retry_after_seconds(ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many login attempts; try again in {retry} seconds",
            headers={"Retry-After": str(retry)},
        )

    # Always record the attempt BEFORE running verify, so a brute-forcer
    # cannot fire faster than the response time of bcrypt.
    rate_limiter.record_attempt(ip)

    user = await get_admin_user(db, "admin")
    stored_hash = user.password_hash if user else None
    if not verify_password(payload.password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    _set_session(request, user.username)
    await update_last_login(db, user.username)
    logger.info("auth: admin login from %s", ip)
    return {"ok": True, "username": user.username}


@router.post("/logout")
async def logout(request: Request) -> dict:
    """Clear the session cookie."""
    request.session.clear()
    return {"ok": True}
