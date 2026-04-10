"""Admin endpoints for managing encrypted secrets.

All routes here are gated by `require_admin`. None of them ever return
plaintext secret values; the GET endpoint returns only key names plus
"is_set" / "updated_at" status, and the audit endpoint returns metadata.

PUT and DELETE trigger a hot reload of the affected provider so the
new credential takes effect immediately, without a backend restart.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.auth.middleware import require_admin
from app.lifecycle.providers import rebuild_for_key
from app.vault import audit
from app.vault.keys import SECRET_KEYS, SECRET_KEY_NAMES, SecretKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class SecretView(BaseModel):
    """View of a vault entry returned to the Settings UI.

    For secret entries (API tokens, OAuth secrets), `value` is always None
    no matter what is stored. For non-secret entries (subdomains, usernames),
    `value` is the decrypted current value so the UI can pre-fill the input.
    Both kinds are stored encrypted; the difference is whether the plaintext
    is allowed to leave the backend.
    """
    key: str
    label: str
    provider: str
    is_set: bool
    secret: bool
    value: str | None
    updated_at: str | None


class SecretSetRequest(BaseModel):
    value: str = Field(min_length=1)


class SecretMutationResponse(BaseModel):
    ok: bool
    key: str
    reload: dict


class AuditEntry(BaseModel):
    ts: str
    actor: str
    action: str
    key: str
    ip: str | None
    user_agent: str | None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _validate_key(key: str) -> SecretKey:
    if key not in SECRET_KEY_NAMES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown secret key: {key}",
        )
    return next(sk for sk in SECRET_KEYS if sk.name == key)


@router.get("/secrets", response_model=list[SecretView])
async def list_secrets(
    request: Request, _: str = Depends(require_admin)
) -> list[SecretView]:
    """Return the configured credential slots.

    Secret entries (API tokens) come back with value=None. Non-secret
    entries (subdomains, usernames) come back with their decrypted value
    so the Settings UI can pre-fill the input field.
    """
    vault = request.app.state.vault
    statuses = await vault.list_status()
    set_map = {s.key: s for s in statuses}

    out: list[SecretView] = []
    for sk in SECRET_KEYS:
        s = set_map.get(sk.name)
        is_set = s is not None
        value: str | None = None
        if is_set and not sk.secret:
            value = await vault.get(sk.name)
        out.append(
            SecretView(
                key=sk.name,
                label=sk.label,
                provider=sk.provider,
                is_set=is_set,
                secret=sk.secret,
                value=value,
                updated_at=s.updated_at if s else None,
            )
        )
    return out


@router.put("/secrets/{key}", response_model=SecretMutationResponse)
async def set_secret(
    key: str,
    payload: SecretSetRequest,
    request: Request,
    actor: str = Depends(require_admin),
) -> SecretMutationResponse:
    """Encrypt and store a secret, then hot-reload the affected provider."""
    sk = _validate_key(key)
    vault = request.app.state.vault
    await vault.set(
        sk.name,
        payload.value,
        actor=actor,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    reload_result = await rebuild_for_key(request.app, sk.name)
    return SecretMutationResponse(ok=True, key=sk.name, reload=reload_result)


@router.delete("/secrets/{key}", response_model=SecretMutationResponse)
async def delete_secret(
    key: str,
    request: Request,
    actor: str = Depends(require_admin),
) -> SecretMutationResponse:
    """Remove a secret. The next sync will fail until a new value is set."""
    sk = _validate_key(key)
    vault = request.app.state.vault
    deleted = await vault.delete(
        sk.name,
        actor=actor,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"secret {key} was not set",
        )
    reload_result = await rebuild_for_key(request.app, sk.name)
    return SecretMutationResponse(ok=True, key=sk.name, reload=reload_result)


@router.get("/audit", response_model=list[AuditEntry])
async def list_audit(
    request: Request,
    limit: int = 50,
    _: str = Depends(require_admin),
) -> list[AuditEntry]:
    """Return the most recent audit events for the secrets store."""
    if limit < 1 or limit > 500:
        limit = 50
    db = request.app.state.db
    conn = await db.get_connection()
    rows = await audit.list_recent(conn, limit=limit)
    return [AuditEntry(**r) for r in rows]
