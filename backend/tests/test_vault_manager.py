"""Integration tests for SecretsManager backed by a temporary SQLite file."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from app.database import Database
from app.vault import crypto
from app.vault.manager import SecretsManager


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def kek() -> bytes:
    return crypto.generate_kek()


@pytest.fixture
async def manager(db: Database, kek: bytes) -> SecretsManager:
    return SecretsManager(db, kek)


async def test_set_and_get_roundtrip(manager: SecretsManager):
    await manager.set("superops.api_token", "secret-value-1", actor="test")
    assert await manager.get("superops.api_token") == "secret-value-1"


async def test_get_missing_returns_none(manager: SecretsManager):
    assert await manager.get("does.not.exist") is None


async def test_has_reflects_state(manager: SecretsManager):
    assert not await manager.has("k")
    await manager.set("k", "v", actor="test")
    assert await manager.has("k")


async def test_set_overwrites(manager: SecretsManager):
    await manager.set("k", "v1", actor="test")
    await manager.set("k", "v2", actor="test")
    assert await manager.get("k") == "v2"


async def test_delete_removes_secret(manager: SecretsManager):
    await manager.set("k", "v", actor="test")
    deleted = await manager.delete("k", actor="test")
    assert deleted is True
    assert await manager.get("k") is None


async def test_delete_missing_returns_false(manager: SecretsManager):
    assert await manager.delete("nope", actor="test") is False


async def test_list_status_excludes_values(manager: SecretsManager):
    await manager.set("a", "value-a", actor="test")
    await manager.set("b", "value-b", actor="test")
    statuses = await manager.list_status()
    keys = {s.key for s in statuses}
    assert keys == {"a", "b"}
    # SecretStatus is a dataclass; verify no value attribute leaks plaintext
    for s in statuses:
        assert not hasattr(s, "value")
        assert s.is_set is True
        assert s.updated_at


async def test_ciphertext_does_not_contain_plaintext(
    manager: SecretsManager, db: Database
):
    plaintext = "this-is-the-secret-value"
    await manager.set("k", plaintext, actor="test")
    conn = await db.get_connection()
    cursor = await conn.execute("SELECT ciphertext FROM vault_secrets WHERE key = 'k'")
    row = await cursor.fetchone()
    assert row is not None
    assert plaintext.encode("utf-8") not in row[0]


async def test_set_writes_audit_row(manager: SecretsManager, db: Database):
    await manager.set("k", "v", actor="alice", ip="1.2.3.4")
    conn = await db.get_connection()
    cursor = await conn.execute(
        "SELECT actor, action, key, ip FROM secrets_audit WHERE key = 'k'"
    )
    rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "alice"
    assert rows[0][1] == "set"
    assert rows[0][2] == "k"
    assert rows[0][3] == "1.2.3.4"


async def test_audit_does_not_contain_plaintext(
    manager: SecretsManager, db: Database
):
    await manager.set("k", "leaky-secret", actor="test")
    await manager.delete("k", actor="test")
    conn = await db.get_connection()
    cursor = await conn.execute("SELECT * FROM secrets_audit")
    rows = await cursor.fetchall()
    for row in rows:
        for col in row:
            if isinstance(col, (str, bytes)):
                assert b"leaky-secret" not in (
                    col.encode() if isinstance(col, str) else col
                )


async def test_dek_persists_across_manager_instances(
    db: Database, kek: bytes
):
    """Two managers sharing the same DB and KEK can read each other's writes."""
    m1 = SecretsManager(db, kek)
    await m1.set("k", "v", actor="t")

    m2 = SecretsManager(db, kek)
    assert await m2.get("k") == "v"


async def test_wrong_kek_cannot_decrypt(db: Database, kek: bytes):
    m1 = SecretsManager(db, kek)
    await m1.set("k", "v", actor="t")

    other_kek = crypto.generate_kek()
    m2 = SecretsManager(db, other_kek)
    with pytest.raises(crypto.DekUnwrapError):
        await m2.get("k")


async def test_rotate_kek_preserves_secrets(db: Database, kek: bytes):
    m1 = SecretsManager(db, kek)
    await m1.set("a", "alpha", actor="t")
    await m1.set("b", "beta", actor="t")

    new_kek = crypto.generate_kek()
    await m1.rotate_kek(new_kek)

    # New manager using the new KEK should still read the same secrets.
    m2 = SecretsManager(db, new_kek)
    assert await m2.get("a") == "alpha"
    assert await m2.get("b") == "beta"

    # Old KEK should now fail to unwrap the DEK.
    m3 = SecretsManager(db, kek)
    with pytest.raises(crypto.DekUnwrapError):
        await m3.get("a")
