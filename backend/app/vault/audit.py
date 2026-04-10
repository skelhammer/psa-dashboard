"""Audit logging for secret mutations.

Audit events are written to two places:
1. The `secrets_audit` SQLite table (queryable from the admin UI).
2. An append-only JSON line file (`logs/secrets_audit.log`) via
   WatchedFileHandler so a DB-level compromise cannot silently erase the trail.

Only mutation events (set, delete, rotate, migrate, login) are logged. Reads
are NOT audited because every page render of the dashboard would call get(),
which would balloon the log and obscure real activity. Reads of decrypted
values are protected by the admin auth gate, not by audit.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

_audit_logger: logging.Logger | None = None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configure_file_logger(log_path: Path) -> None:
    """Set up the append-only audit file logger.

    Idempotent: safe to call repeatedly. Uses WatchedFileHandler so log
    rotation tools (logrotate) can move the file without restarting the app.
    """
    global _audit_logger
    if _audit_logger is not None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.WatchedFileHandler(str(log_path), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("psa_dashboard.vault.audit")
    logger.setLevel(logging.INFO)
    # Do not propagate to root; we want the audit trail to be deliberate,
    # not interleaved into the app log.
    logger.propagate = False
    logger.addHandler(handler)
    _audit_logger = logger
    # Best-effort tighten file mode on POSIX. On Windows this is a no-op.
    try:
        import os
        import stat
        os.chmod(log_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
    except Exception:
        pass


async def record(
    conn: aiosqlite.Connection,
    *,
    actor: str,
    action: str,
    key: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append an audit event to both the DB table and the audit log file.

    Never include the secret value in `key` or anywhere else; this function
    only records metadata (who, what action, which key name).
    """
    ts = _iso_now()
    await conn.execute(
        "INSERT INTO secrets_audit (ts, actor, action, key, ip, user_agent) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ts, actor, action, key, ip, user_agent),
    )
    if _audit_logger is not None:
        _audit_logger.info(
            json.dumps(
                {
                    "ts": ts,
                    "actor": actor,
                    "action": action,
                    "key": key,
                    "ip": ip,
                    "user_agent": user_agent,
                },
                separators=(",", ":"),
            )
        )


async def list_recent(
    conn: aiosqlite.Connection, limit: int = 50
) -> list[dict]:
    """Return the most recent audit events, newest first."""
    cursor = await conn.execute(
        "SELECT ts, actor, action, key, ip, user_agent FROM secrets_audit "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "ts": r[0],
            "actor": r[1],
            "action": r[2],
            "key": r[3],
            "ip": r[4],
            "user_agent": r[5],
        }
        for r in rows
    ]


async def prune_older_than(conn: aiosqlite.Connection, days: int) -> int:
    """Delete audit rows older than `days`. Returns number of rows removed."""
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat(
        timespec="seconds"
    )
    cursor = await conn.execute(
        "DELETE FROM secrets_audit WHERE ts < ?", (cutoff_iso,)
    )
    return cursor.rowcount or 0
