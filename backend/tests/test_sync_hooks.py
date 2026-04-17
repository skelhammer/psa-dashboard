"""Tests for post-sync hooks provider scoping.

These confirm that running the hooks after one provider's sync never
mutates rows belonging to other providers. The core guarantee is
multi-provider isolation via the `provider` column plus ID prefixing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from app import config as app_config
from app.config import Settings
from app.database import Database
from app.sync.hooks import (
    backfill_resolution_time,
    generate_billing_flags,
    sync_billing_config,
)


@pytest.fixture
async def db(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture(autouse=True)
def _default_settings():
    """Force get_settings() to return a fresh default Settings for each test.

    The hooks call get_settings() which caches a module-level singleton
    populated from config.yaml at first access; tests must use the defaults
    (empty unlimited_plans, empty flags_start_date) unless they override.
    """
    original = app_config._settings
    app_config._settings = Settings()
    try:
        yield app_config._settings
    finally:
        app_config._settings = original


async def _insert_client(conn, provider: str, client_id: str, name: str, plan: str = ""):
    await conn.execute(
        """INSERT INTO clients (id, name, plan, stage, provider)
           VALUES (?, ?, ?, 'Active', ?)""",
        (client_id, name, plan or None, provider),
    )


async def _insert_ticket(
    conn,
    provider: str,
    ticket_id: str,
    client_id: str,
    status: str = "Resolved",
    worklog_hours: float = 0,
    resolution_time: str | None = None,
):
    now = datetime.now().isoformat()
    await conn.execute(
        """INSERT INTO tickets (
            id, display_id, subject, client_id, status, priority,
            created_time, updated_time, resolution_time, worklog_hours,
            provider, synced_at
        ) VALUES (?, ?, ?, ?, ?, 'Medium', ?, ?, ?, ?, ?, ?)""",
        (
            ticket_id,
            ticket_id.split(":", 1)[1] if ":" in ticket_id else ticket_id,
            "Test ticket",
            client_id,
            status,
            now,
            now,
            resolution_time,
            worklog_hours,
            provider,
            now,
        ),
    )


async def _insert_contract(
    conn, provider: str, contract_id: str, client_id: str, contract_name: str
):
    now = datetime.now().isoformat()
    await conn.execute(
        """INSERT INTO client_contracts (
            contract_id, client_id, client_name, contract_type,
            contract_name, status, provider, synced_at
        ) VALUES (?, ?, '', 'other', ?, 'active', ?, ?)""",
        (contract_id, client_id, contract_name, provider, now),
    )


async def test_backfill_resolution_time_scoped_to_provider(db):
    conn = await db.get_connection()
    await _insert_client(conn, "superops", "superops:c1", "SO Corp")
    await _insert_client(conn, "zendesk", "zendesk:c1", "ZD Corp")
    await _insert_ticket(
        conn, "superops", "superops:t1", "superops:c1",
        status="Resolved", resolution_time=None,
    )
    await _insert_ticket(
        conn, "zendesk", "zendesk:t1", "zendesk:c1",
        status="Resolved", resolution_time=None,
    )
    await conn.commit()

    # Run scoped to superops only
    await backfill_resolution_time(conn, provider_name="superops")

    # SuperOps ticket should have resolution_time backfilled from updated_time
    rows = await conn.execute_fetchall(
        "SELECT id, resolution_time FROM tickets ORDER BY id"
    )
    by_id = {r[0]: r[1] for r in rows}
    assert by_id["superops:t1"] is not None
    assert by_id["zendesk:t1"] is None


async def test_sync_billing_config_scoped_to_provider(db):
    conn = await db.get_connection()
    await _insert_client(conn, "superops", "superops:c1", "SO Corp")
    await _insert_client(conn, "zendesk", "zendesk:c1", "ZD Corp")
    await conn.commit()

    # Only SuperOps syncing should not create config for Zendesk clients
    await sync_billing_config(conn, provider_name="superops")

    rows = await conn.execute_fetchall(
        "SELECT client_id FROM billing_config ORDER BY client_id"
    )
    client_ids = {r[0] for r in rows}
    assert "superops:c1" in client_ids
    assert "zendesk:c1" not in client_ids


async def test_sync_billing_config_unlimited_plan_scoped(db, monkeypatch):
    """Unlimited-plan exclusion scoped to the syncing provider.

    If SuperOps has a client on an unlimited plan but Zendesk also has one
    with the same plan name, a SuperOps sync must only delete/skip the
    SuperOps client's billing config, not Zendesk's.
    """
    conn = await db.get_connection()

    # Both providers have a client on the same "Managed Plan A" unlimited plan
    await _insert_client(
        conn, "superops", "superops:c1", "SO Unlimited", plan="Managed Plan A"
    )
    await _insert_client(
        conn, "zendesk", "zendesk:c1", "ZD Unlimited", plan="Managed Plan A"
    )
    # Zendesk's client already has an auto_detected billing_config row
    # (simulating a previous Zendesk sync ran and set it up).
    await conn.execute(
        """INSERT INTO billing_config
           (client_id, billing_type, auto_detected, updated_at)
           VALUES (?, 'hourly', 1, ?)""",
        ("zendesk:c1", datetime.now().isoformat()),
    )
    await conn.commit()

    # Settings with unlimited_plans set
    app_config._settings.billing.unlimited_plans = ["Managed Plan A"]

    # SuperOps sync runs. It should only scope unlimited-plan handling to
    # its own clients. Zendesk's billing_config row must remain intact.
    await sync_billing_config(conn, provider_name="superops")

    rows = await conn.execute_fetchall(
        "SELECT client_id FROM billing_config ORDER BY client_id"
    )
    client_ids = {r[0] for r in rows}
    # Zendesk's existing row is untouched despite matching an unlimited plan
    assert "zendesk:c1" in client_ids
    # SuperOps' client on an unlimited plan is NOT billable
    assert "superops:c1" not in client_ids


async def test_generate_billing_flags_scoped_to_provider(db):
    """Flags only created for tickets of the syncing provider."""
    conn = await db.get_connection()
    await _insert_client(conn, "superops", "superops:c1", "SO Corp")
    await _insert_client(conn, "zendesk", "zendesk:c1", "ZD Corp")

    # Both providers' clients are billable
    now = datetime.now().isoformat()
    for cid in ("superops:c1", "zendesk:c1"):
        await conn.execute(
            """INSERT INTO billing_config
               (client_id, billing_type, track_billing, auto_detected, updated_at)
               VALUES (?, 'hourly', 1, 1, ?)""",
            (cid, now),
        )

    # Each provider has one resolved ticket with 0 worklog (should flag)
    await _insert_ticket(
        conn, "superops", "superops:t1", "superops:c1",
        status="Resolved", worklog_hours=0,
    )
    await _insert_ticket(
        conn, "zendesk", "zendesk:t1", "zendesk:c1",
        status="Resolved", worklog_hours=0,
    )
    await conn.commit()

    await generate_billing_flags(conn, provider_name="superops")

    rows = await conn.execute_fetchall(
        "SELECT ticket_id, flag_type FROM billing_flags ORDER BY ticket_id"
    )
    flagged = {r[0] for r in rows}
    # Only the SuperOps ticket was flagged; Zendesk's wasn't touched
    assert "superops:t1" in flagged
    assert "zendesk:t1" not in flagged


async def test_generate_billing_flags_auto_resolve_scoped(db):
    """Auto-resolve updates stay within the syncing provider.

    If a Zendesk ticket has an open MISSING_WORKLOG flag and it now has
    worklog_hours > 0, a SuperOps sync must NOT auto-resolve that flag.
    Only the Zendesk sync should clean it up.
    """
    conn = await db.get_connection()
    await _insert_client(conn, "superops", "superops:c1", "SO Corp")
    await _insert_client(conn, "zendesk", "zendesk:c1", "ZD Corp")

    now = datetime.now().isoformat()
    for cid in ("superops:c1", "zendesk:c1"):
        await conn.execute(
            """INSERT INTO billing_config
               (client_id, billing_type, track_billing, auto_detected, updated_at)
               VALUES (?, 'hourly', 1, 1, ?)""",
            (cid, now),
        )

    # Zendesk ticket now has worklog hours, so its flag should be eligible
    # for auto-resolution but only when Zendesk syncs.
    await _insert_ticket(
        conn, "zendesk", "zendesk:t1", "zendesk:c1",
        status="Resolved", worklog_hours=2.0,
    )
    await conn.execute(
        """INSERT INTO billing_flags
           (ticket_id, flag_type, flag_reason, flagged_at, resolved)
           VALUES ('zendesk:t1', 'MISSING_WORKLOG', 'orig', ?, 0)""",
        (now,),
    )
    await conn.commit()

    # A SuperOps sync runs. Zendesk's flag must remain unresolved.
    await generate_billing_flags(conn, provider_name="superops")

    row = await conn.execute_fetchall(
        "SELECT resolved FROM billing_flags WHERE ticket_id = 'zendesk:t1'"
    )
    assert row[0][0] == 0

    # Now Zendesk syncs; the flag should resolve.
    await generate_billing_flags(conn, provider_name="zendesk")
    row = await conn.execute_fetchall(
        "SELECT resolved FROM billing_flags WHERE ticket_id = 'zendesk:t1'"
    )
    assert row[0][0] == 1


async def test_hooks_empty_provider_name_is_unscoped(db):
    """Passing provider_name='' (legacy / CLI) mutates all providers.

    This preserves backward-compatible behavior for callers that don't
    know the current provider.
    """
    conn = await db.get_connection()
    await _insert_client(conn, "superops", "superops:c1", "SO Corp")
    await _insert_client(conn, "zendesk", "zendesk:c1", "ZD Corp")
    await _insert_ticket(
        conn, "superops", "superops:t1", "superops:c1",
        status="Resolved", resolution_time=None,
    )
    await _insert_ticket(
        conn, "zendesk", "zendesk:t1", "zendesk:c1",
        status="Resolved", resolution_time=None,
    )
    await conn.commit()

    await backfill_resolution_time(conn, provider_name="")

    rows = await conn.execute_fetchall("SELECT id, resolution_time FROM tickets")
    # All resolution_times backfilled
    assert all(r[1] is not None for r in rows)
