"""Tests for the admin users module, focused on the setup-race guarantee.

The admin-setup endpoint must create exactly one admin even when two
concurrent requests both pass the any_admin_exists() check before the
first commits. create_admin_user_if_none_exists uses an atomic
INSERT ... SELECT ... WHERE NOT EXISTS so SQLite evaluates the guard
and the insert in a single statement.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.auth.users import (
    any_admin_exists,
    create_admin_user_if_none_exists,
    get_admin_user,
)
from app.database import Database


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


async def test_create_admin_creates_when_none_exist(db):
    assert not await any_admin_exists(db)
    user = await create_admin_user_if_none_exists(db, "admin", "hash-1")
    assert user is not None
    assert user.username == "admin"
    assert user.role == "admin"
    assert await any_admin_exists(db)


async def test_create_admin_returns_none_on_second_call(db):
    first = await create_admin_user_if_none_exists(db, "admin", "hash-1")
    assert first is not None

    # Second call must not replace the original. The hash stays hash-1.
    second = await create_admin_user_if_none_exists(db, "admin", "hash-2")
    assert second is None

    stored = await get_admin_user(db, "admin")
    assert stored is not None
    assert stored.password_hash == "hash-1"


async def test_concurrent_setup_only_one_wins(db):
    """asyncio.gather() two create calls; exactly one returns the user row.

    aiosqlite serializes at the connection level, so this effectively
    simulates two requests competing for the same DB. The guarantee we
    care about is: no IntegrityError bubbles up, exactly one succeeds.
    """
    results = await asyncio.gather(
        create_admin_user_if_none_exists(db, "admin", "hash-a"),
        create_admin_user_if_none_exists(db, "admin", "hash-b"),
    )
    succeeded = [r for r in results if r is not None]
    failed = [r for r in results if r is None]
    assert len(succeeded) == 1
    assert len(failed) == 1

    # Whichever won, the stored hash is one of the two we tried
    stored = await get_admin_user(db, "admin")
    assert stored is not None
    assert stored.password_hash in ("hash-a", "hash-b")
