"""SQLite database management. PSA-agnostic schema."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    display_id TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    ticket_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    client_id TEXT NOT NULL DEFAULT '',
    client_name TEXT NOT NULL DEFAULT '',
    site_id TEXT,
    site_name TEXT,
    requester_id TEXT NOT NULL DEFAULT '',
    requester_name TEXT NOT NULL DEFAULT 'Unknown',
    tech_group_id TEXT,
    tech_group_name TEXT,
    technician_id TEXT,
    technician_name TEXT,
    status TEXT NOT NULL DEFAULT 'Open',
    priority TEXT NOT NULL DEFAULT 'Medium',
    impact TEXT,
    urgency TEXT,
    category TEXT,
    subcategory TEXT,
    sla_id TEXT,
    sla_name TEXT,
    created_time TEXT NOT NULL,
    updated_time TEXT NOT NULL,
    first_response_due TEXT,
    first_response_time TEXT,
    first_response_violated INTEGER,
    resolution_due TEXT,
    resolution_time TEXT,
    resolution_violated INTEGER,
    worklog_hours INTEGER NOT NULL DEFAULT 0,
    conversation_count INTEGER NOT NULL DEFAULT 0,
    tech_reply_count INTEGER NOT NULL DEFAULT 0,
    last_conversation_time TEXT,
    last_responder_type TEXT,
    reopened INTEGER NOT NULL DEFAULT 0,
    first_response_business_minutes REAL,
    resolution_business_minutes REAL,
    provider TEXT NOT NULL DEFAULT 'superops',
    is_corp INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS technicians (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    available_hours_per_week REAL NOT NULL DEFAULT 40.0,
    provider TEXT NOT NULL DEFAULT 'superops'
);

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    plan TEXT,
    stage TEXT,
    status TEXT,
    profit_type TEXT,
    account_number TEXT,
    provider TEXT NOT NULL DEFAULT 'superops'
);

CREATE TABLE IF NOT EXISTS client_contracts (
    contract_id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL,
    client_name TEXT NOT NULL DEFAULT '',
    contract_type TEXT NOT NULL DEFAULT 'other',
    contract_name TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    start_date TEXT,
    end_date TEXT,
    provider TEXT NOT NULL DEFAULT 'superops',
    synced_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS billing_config (
    client_id TEXT PRIMARY KEY,
    billing_type TEXT NOT NULL DEFAULT 'other',
    hourly_rate REAL,
    minimum_bill_minutes INTEGER NOT NULL DEFAULT 15,
    track_billing INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    auto_detected INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE IF NOT EXISTS billing_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    flag_type TEXT NOT NULL,
    flag_reason TEXT NOT NULL DEFAULT '',
    flagged_at TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_note TEXT,
    FOREIGN KEY (ticket_id) REFERENCES tickets(id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    tickets_synced INTEGER NOT NULL DEFAULT 0,
    errors TEXT,
    provider_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS dashboard_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

-- Default dashboard config values
INSERT OR IGNORE INTO dashboard_config (key, value) VALUES
    ('stale_ticket_threshold_days', '3'),
    ('sla_warning_minutes', '30'),
    ('work_queue_sla_violated_weight', '1000'),
    ('work_queue_sla_30min_weight', '500'),
    ('work_queue_sla_2hr_weight', '200'),
    ('work_queue_sla_safe_weight', '0'),
    ('work_queue_priority_critical_weight', '100'),
    ('work_queue_priority_high_weight', '75'),
    ('work_queue_priority_medium_weight', '50'),
    ('work_queue_priority_low_weight', '25'),
    ('work_queue_age_weight_per_hour', '1'),
    ('mtz_yellow_pct', '2'),
    ('mtz_red_pct', '5'),
    ('mtz_yellow_floor', '2'),
    ('mtz_red_floor', '5'),
    ('stale_exclude_statuses', 'Waiting on Customer,Waiting on Vendor,Scheduled');

CREATE INDEX IF NOT EXISTS idx_tickets_provider ON tickets(provider);
CREATE INDEX IF NOT EXISTS idx_tickets_fr_biz_min ON tickets(first_response_business_minutes);
CREATE INDEX IF NOT EXISTS idx_tickets_res_biz_min ON tickets(resolution_business_minutes);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_technician_id ON tickets(technician_id);
CREATE INDEX IF NOT EXISTS idx_tickets_client_id ON tickets(client_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created_time ON tickets(created_time);
CREATE INDEX IF NOT EXISTS idx_tickets_updated_time ON tickets(updated_time);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_billing_flags_ticket_id ON billing_flags(ticket_id);
CREATE INDEX IF NOT EXISTS idx_billing_flags_resolved ON billing_flags(resolved);
CREATE INDEX IF NOT EXISTS idx_client_contracts_client_id ON client_contracts(client_id);

-- Phone integration tables
CREATE TABLE IF NOT EXISTS phone_calls (
    id TEXT PRIMARY KEY,
    direction TEXT,
    caller_number TEXT,
    caller_name TEXT,
    callee_number TEXT,
    callee_name TEXT,
    start_time TEXT,
    answer_time TEXT,
    end_time TEXT,
    duration INTEGER,
    wait_time INTEGER,
    hold_time INTEGER,
    result TEXT,
    user_id TEXT,
    user_email TEXT,
    queue_id TEXT,
    queue_name TEXT,
    has_recording INTEGER DEFAULT 0,
    has_voicemail INTEGER DEFAULT 0,
    matched_client_id TEXT,
    matched_ticket_id TEXT,
    is_internal INTEGER DEFAULT 0,
    synced_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS phone_users (
    id TEXT PRIMARY KEY,
    email TEXT,
    name TEXT,
    extension TEXT,
    department TEXT,
    status TEXT,
    synced_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS phone_queues (
    id TEXT PRIMARY KEY,
    name TEXT,
    extension TEXT,
    member_count INTEGER,
    synced_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS phone_agent_daily (
    date TEXT,
    user_id TEXT,
    user_email TEXT,
    total_calls INTEGER DEFAULT 0,
    inbound_calls INTEGER DEFAULT 0,
    outbound_calls INTEGER DEFAULT 0,
    answered_calls INTEGER DEFAULT 0,
    missed_calls INTEGER DEFAULT 0,
    voicemail_calls INTEGER DEFAULT 0,
    abandoned_calls INTEGER DEFAULT 0,
    total_talk_seconds INTEGER DEFAULT 0,
    total_wait_seconds INTEGER DEFAULT 0,
    total_hold_seconds INTEGER DEFAULT 0,
    avg_handle_seconds INTEGER DEFAULT 0,
    PRIMARY KEY (date, user_id)
);

CREATE INDEX IF NOT EXISTS idx_phone_calls_start_time ON phone_calls(start_time);
CREATE INDEX IF NOT EXISTS idx_phone_calls_user_id ON phone_calls(user_id);
CREATE INDEX IF NOT EXISTS idx_phone_calls_queue_id ON phone_calls(queue_id);
CREATE INDEX IF NOT EXISTS idx_phone_calls_result ON phone_calls(result);
CREATE INDEX IF NOT EXISTS idx_phone_agent_daily_date ON phone_agent_daily(date);
CREATE INDEX IF NOT EXISTS idx_phone_calls_caller_inbound ON phone_calls(caller_number, direction, start_time);
CREATE INDEX IF NOT EXISTS idx_phone_calls_sl ON phone_calls(direction, result, wait_time);
CREATE INDEX IF NOT EXISTS idx_phone_calls_internal ON phone_calls(is_internal);

-- Manage to Zero trend snapshots
CREATE TABLE IF NOT EXISTS mtz_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    card_key TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mtz_snapshots_recorded ON mtz_snapshots(recorded_at);
CREATE INDEX IF NOT EXISTS idx_mtz_snapshots_card ON mtz_snapshots(card_key, recorded_at);

-- Alerts and metric snapshots
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    entity_type TEXT,
    entity_id TEXT,
    created_at TEXT NOT NULL,
    acknowledged_at TEXT,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    date TEXT,
    metric_name TEXT,
    value REAL,
    PRIMARY KEY (date, metric_name)
);

-- Vault: encrypted secrets store
CREATE TABLE IF NOT EXISTS vault_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    wrapped_dek BLOB NOT NULL,
    dek_nonce BLOB NOT NULL,
    kek_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_secrets (
    key TEXT PRIMARY KEY,
    nonce BLOB NOT NULL,
    ciphertext BLOB NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secrets_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    key TEXT NOT NULL,
    ip TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_secrets_audit_ts ON secrets_audit(ts);

CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
"""


MIGRATIONS = [
    "ALTER TABLE tickets ADD COLUMN first_response_business_minutes REAL",
    "ALTER TABLE tickets ADD COLUMN resolution_business_minutes REAL",
    "ALTER TABLE billing_config ADD COLUMN monthly_contract_value REAL",
    "ALTER TABLE technicians ADD COLUMN dashboard_role TEXT NOT NULL DEFAULT 'technician'",
    "ALTER TABLE tickets RENAME COLUMN worklog_minutes TO worklog_hours",
    # Multi-provider support: add provider column to entity tables
    "ALTER TABLE tickets ADD COLUMN provider TEXT NOT NULL DEFAULT 'superops'",
    # Corp ticket tagging (Zendesk custom field)
    "ALTER TABLE tickets ADD COLUMN is_corp INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE technicians ADD COLUMN provider TEXT NOT NULL DEFAULT 'superops'",
    "ALTER TABLE clients ADD COLUMN provider TEXT NOT NULL DEFAULT 'superops'",
    "ALTER TABLE client_contracts ADD COLUMN provider TEXT NOT NULL DEFAULT 'superops'",
    # Phone analytics enhancements
    "ALTER TABLE phone_calls ADD COLUMN is_internal INTEGER DEFAULT 0",
    "ALTER TABLE phone_agent_daily ADD COLUMN abandoned_calls INTEGER DEFAULT 0",
    # First Call Resolution custom field
    "ALTER TABLE tickets ADD COLUMN fcr INTEGER NOT NULL DEFAULT 0",
    # Contract management: manual entries, term length, salesperson notes
    "ALTER TABLE client_contracts ADD COLUMN term_length_years INTEGER",
    "ALTER TABLE client_contracts ADD COLUMN source TEXT NOT NULL DEFAULT 'synced'",
    "ALTER TABLE client_contracts ADD COLUMN notes TEXT",
]


async def _migrate_prefix_ids(conn: aiosqlite.Connection):
    """One-time migration: prefix existing IDs with 'superops:' for multi-provider support.

    Idempotent: skips rows that already contain a ':' in the ID.
    Updates all foreign key references in a single transaction.
    """
    # Check if any unprefixed tickets exist
    rows = await conn.execute_fetchall(
        "SELECT COUNT(*) FROM tickets WHERE id NOT LIKE '%:%'"
    )
    if not rows or rows[0][0] == 0:
        return  # Already migrated or empty database

    logger.info("Migrating existing IDs to 'superops:' prefix for multi-provider support...")

    # Prefix ticket IDs and their foreign key references
    await conn.execute(
        """UPDATE tickets SET
            id = 'superops:' || id,
            client_id = CASE WHEN client_id != '' THEN 'superops:' || client_id ELSE client_id END,
            technician_id = CASE WHEN technician_id IS NOT NULL AND technician_id != '' THEN 'superops:' || technician_id ELSE technician_id END,
            requester_id = CASE WHEN requester_id != '' THEN 'superops:' || requester_id ELSE requester_id END,
            tech_group_id = CASE WHEN tech_group_id IS NOT NULL AND tech_group_id != '' THEN 'superops:' || tech_group_id ELSE tech_group_id END,
            sla_id = CASE WHEN sla_id IS NOT NULL AND sla_id != '' THEN 'superops:' || sla_id ELSE sla_id END,
            provider = 'superops'
        WHERE id NOT LIKE '%:%'"""
    )

    # Prefix technician IDs
    await conn.execute(
        """UPDATE technicians SET
            id = 'superops:' || id,
            provider = 'superops'
        WHERE id NOT LIKE '%:%'"""
    )

    # Prefix client IDs
    await conn.execute(
        """UPDATE clients SET
            id = 'superops:' || id,
            provider = 'superops'
        WHERE id NOT LIKE '%:%'"""
    )

    # Prefix contract IDs and client references
    await conn.execute(
        """UPDATE client_contracts SET
            contract_id = 'superops:' || contract_id,
            client_id = CASE WHEN client_id NOT LIKE '%:%' THEN 'superops:' || client_id ELSE client_id END,
            provider = 'superops'
        WHERE contract_id NOT LIKE '%:%'"""
    )

    # Prefix billing_config client references
    await conn.execute(
        """UPDATE billing_config SET
            client_id = 'superops:' || client_id
        WHERE client_id NOT LIKE '%:%'"""
    )

    # Prefix billing_flags ticket references
    await conn.execute(
        """UPDATE billing_flags SET
            ticket_id = 'superops:' || ticket_id
        WHERE ticket_id NOT LIKE '%:%'"""
    )

    await conn.commit()
    logger.info("ID prefix migration complete")


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self):
        """Create database directory and initialize schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
        # Run migrations first so columns exist before CREATE INDEX
        await self._run_migrations()
        await self._connection.executescript(SCHEMA_SQL)
        await self._connection.commit()
        # Prefix existing IDs for multi-provider support (idempotent)
        await _migrate_prefix_ids(self._connection)
        logger.info("Database initialized at %s", self.db_path)

    async def _run_migrations(self):
        """Apply column-add migrations for existing databases.

        Each statement is wrapped in try/except because SQLite does not
        support IF NOT EXISTS for ALTER TABLE ADD COLUMN.
        """
        for sql in MIGRATIONS:
            try:
                await self._connection.execute(sql)
                await self._connection.commit()
                logger.info("Migration applied: %s", sql)
            except Exception:
                # Column likely already exists; safe to ignore.
                pass

    async def get_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            await self.initialize()
        return self._connection

    async def close(self):
        if self._connection:
            await self._connection.close()
            self._connection = None


# Singleton
_db: Database | None = None


def get_database(db_path: Path | None = None) -> Database:
    global _db
    if _db is None:
        if db_path is None:
            from app.config import get_settings
            db_path = get_settings().db_path
        _db = Database(db_path)
    return _db
