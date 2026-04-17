"""Users table operations.

The dashboard currently uses exactly one admin user. The schema is forward
compatible with multi-user / multi-role for later, but every code path here
assumes a single admin row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.database import Database


@dataclass
class AdminUser:
    username: str
    password_hash: str
    role: str
    created_at: str
    last_login_at: str | None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def get_admin_user(db: Database, username: str = "admin") -> AdminUser | None:
    """Return the admin user row, or None if not yet created."""
    conn = await db.get_connection()
    cursor = await conn.execute(
        "SELECT username, password_hash, role, created_at, last_login_at "
        "FROM users WHERE username = ?",
        (username,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return AdminUser(
        username=row[0],
        password_hash=row[1],
        role=row[2],
        created_at=row[3],
        last_login_at=row[4],
    )


async def any_admin_exists(db: Database) -> bool:
    """True iff at least one admin row exists. Used to gate /api/auth/setup."""
    conn = await db.get_connection()
    cursor = await conn.execute(
        "SELECT 1 FROM users WHERE role = 'admin' LIMIT 1"
    )
    return (await cursor.fetchone()) is not None


async def create_admin_user(
    db: Database, username: str, password_hash: str
) -> AdminUser:
    """Insert a new admin row. Caller must have already hashed the password."""
    conn = await db.get_connection()
    now = _iso_now()
    await conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) "
        "VALUES (?, ?, 'admin', ?)",
        (username, password_hash, now),
    )
    await conn.commit()
    return AdminUser(
        username=username,
        password_hash=password_hash,
        role="admin",
        created_at=now,
        last_login_at=None,
    )


async def create_admin_user_if_none_exists(
    db: Database, username: str, password_hash: str
) -> AdminUser | None:
    """Atomically create the initial admin user iff no admin exists yet.

    Uses INSERT ... SELECT ... WHERE NOT EXISTS so the existence check and
    the insert happen in a single SQLite statement. Returns None if an
    admin row already existed (i.e. a concurrent request beat us to it).
    Callers should treat None as a 403 condition.
    """
    conn = await db.get_connection()
    now = _iso_now()
    cursor = await conn.execute(
        """INSERT INTO users (username, password_hash, role, created_at)
           SELECT ?, ?, 'admin', ?
           WHERE NOT EXISTS (SELECT 1 FROM users WHERE role = 'admin')""",
        (username, password_hash, now),
    )
    await conn.commit()
    if (cursor.rowcount or 0) == 0:
        return None
    return AdminUser(
        username=username,
        password_hash=password_hash,
        role="admin",
        created_at=now,
        last_login_at=None,
    )


async def update_password(
    db: Database, username: str, new_password_hash: str
) -> bool:
    """Replace an existing user's password hash. Returns True if a row was updated."""
    conn = await db.get_connection()
    cursor = await conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (new_password_hash, username),
    )
    await conn.commit()
    return (cursor.rowcount or 0) > 0


async def update_last_login(db: Database, username: str) -> None:
    conn = await db.get_connection()
    await conn.execute(
        "UPDATE users SET last_login_at = ? WHERE username = ?",
        (_iso_now(), username),
    )
    await conn.commit()
