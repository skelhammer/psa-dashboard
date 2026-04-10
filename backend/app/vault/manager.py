"""SecretsManager: high level API for storing and retrieving encrypted secrets.

Lifecycle:
1. Caller constructs SecretsManager(db, kek). The KEK is held only in this
   instance and never logged.
2. On first use, the manager either loads the existing wrapped DEK from
   `vault_meta` and unwraps it, or generates a new DEK and writes a fresh
   `vault_meta` row. After this, only the unwrapped DEK is held in memory.
3. set/get/delete operate on the `vault_secrets` table. Mutations write an
   audit row in the same transaction.

The DEK is cached on the instance for the process lifetime. Rotating the KEK
(via cli.py rotate-kek) only re-wraps the DEK in `vault_meta`; running
processes continue to use the cached DEK and pick up the new wrapping on
their next restart.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

from app.database import Database
from app.vault import audit, crypto

logger = logging.getLogger(__name__)


@dataclass
class SecretStatus:
    """Public-safe view of a secret. Never includes the value."""
    key: str
    is_set: bool
    updated_at: str | None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SecretsManager:
    def __init__(self, db: Database, kek: bytes):
        if len(kek) != crypto.KEK_BYTES:
            raise crypto.KekInvalidError(
                f"KEK must be {crypto.KEK_BYTES} bytes"
            )
        self._db = db
        self._kek = kek
        self._dek: bytes | None = None

    async def _conn(self) -> aiosqlite.Connection:
        return await self._db.get_connection()

    async def _ensure_dek(self) -> bytes:
        """Load or initialize the DEK. Cached after first call."""
        if self._dek is not None:
            return self._dek
        conn = await self._conn()
        cursor = await conn.execute(
            "SELECT wrapped_dek, dek_nonce FROM vault_meta WHERE id = 1"
        )
        row = await cursor.fetchone()
        if row is None:
            # First boot: mint a fresh DEK and wrap it under the current KEK.
            dek = crypto.generate_dek()
            nonce, wrapped = crypto.wrap_dek(dek, self._kek)
            await conn.execute(
                "INSERT INTO vault_meta (id, wrapped_dek, dek_nonce, kek_version, created_at) "
                "VALUES (1, ?, ?, 1, ?)",
                (wrapped, nonce, _iso_now()),
            )
            await conn.commit()
            logger.info("Vault initialized: new DEK generated and wrapped")
            self._dek = dek
            return dek
        wrapped, nonce = row[0], row[1]
        self._dek = crypto.unwrap_dek(wrapped, nonce, self._kek)
        return self._dek

    async def has(self, key: str) -> bool:
        conn = await self._conn()
        cursor = await conn.execute(
            "SELECT 1 FROM vault_secrets WHERE key = ?", (key,)
        )
        return (await cursor.fetchone()) is not None

    async def get(self, key: str) -> str | None:
        """Return the decrypted secret, or None if not set."""
        conn = await self._conn()
        cursor = await conn.execute(
            "SELECT nonce, ciphertext FROM vault_secrets WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        dek = await self._ensure_dek()
        return crypto.decrypt(row[0], row[1], dek, aad=key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        actor: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Encrypt and store a secret. Overwrites any existing value."""
        if not key or not isinstance(key, str):
            raise ValueError("secret key must be a non-empty string")
        if value is None:
            raise ValueError("secret value must not be None")
        dek = await self._ensure_dek()
        nonce, ciphertext = crypto.encrypt(value, dek, aad=key)
        conn = await self._conn()
        await conn.execute(
            "INSERT INTO vault_secrets (key, nonce, ciphertext, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "nonce = excluded.nonce, "
            "ciphertext = excluded.ciphertext, "
            "updated_at = excluded.updated_at",
            (key, nonce, ciphertext, _iso_now()),
        )
        await audit.record(
            conn,
            actor=actor,
            action="set",
            key=key,
            ip=ip,
            user_agent=user_agent,
        )
        await conn.commit()

    async def delete(
        self,
        key: str,
        *,
        actor: str,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> bool:
        """Remove a secret. Returns True if a row was deleted."""
        conn = await self._conn()
        cursor = await conn.execute(
            "DELETE FROM vault_secrets WHERE key = ?", (key,)
        )
        deleted = (cursor.rowcount or 0) > 0
        if deleted:
            await audit.record(
                conn,
                actor=actor,
                action="delete",
                key=key,
                ip=ip,
                user_agent=user_agent,
            )
        await conn.commit()
        return deleted

    async def list_status(self) -> list[SecretStatus]:
        """Return the status of every stored secret. Never includes values."""
        conn = await self._conn()
        cursor = await conn.execute(
            "SELECT key, updated_at FROM vault_secrets ORDER BY key"
        )
        rows = await cursor.fetchall()
        return [
            SecretStatus(key=r[0], is_set=True, updated_at=r[1]) for r in rows
        ]

    async def rotate_kek(self, new_kek: bytes) -> None:
        """Re-wrap the existing DEK under a new KEK and bump kek_version.

        This is an O(1) operation: only the vault_meta row changes. Per-secret
        ciphertexts are unaffected. The caller is responsible for swapping the
        KEK environment variable and restarting the app afterwards.
        """
        if len(new_kek) != crypto.KEK_BYTES:
            raise crypto.KekInvalidError(
                f"new KEK must be {crypto.KEK_BYTES} bytes"
            )
        dek = await self._ensure_dek()
        nonce, wrapped = crypto.wrap_dek(dek, new_kek)
        conn = await self._conn()
        await conn.execute(
            "UPDATE vault_meta SET wrapped_dek = ?, dek_nonce = ?, "
            "kek_version = kek_version + 1 WHERE id = 1",
            (wrapped, nonce),
        )
        await audit.record(
            conn,
            actor="cli",
            action="rotate_kek",
            key="(vault_meta)",
        )
        await conn.commit()
        logger.info("KEK rotated; vault_meta re-wrapped")
