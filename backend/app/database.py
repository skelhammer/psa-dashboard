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
    worklog_minutes INTEGER NOT NULL DEFAULT 0,
    conversation_count INTEGER NOT NULL DEFAULT 0,
    tech_reply_count INTEGER NOT NULL DEFAULT 0,
    last_conversation_time TEXT,
    last_responder_type TEXT,
    reopened INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS technicians (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    available_hours_per_week REAL NOT NULL DEFAULT 40.0
);

CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT ''
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
    ('work_queue_age_weight_per_hour', '1');

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_technician_id ON tickets(technician_id);
CREATE INDEX IF NOT EXISTS idx_tickets_client_id ON tickets(client_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created_time ON tickets(created_time);
CREATE INDEX IF NOT EXISTS idx_tickets_updated_time ON tickets(updated_time);
CREATE INDEX IF NOT EXISTS idx_tickets_priority ON tickets(priority);
CREATE INDEX IF NOT EXISTS idx_billing_flags_ticket_id ON billing_flags(ticket_id);
CREATE INDEX IF NOT EXISTS idx_billing_flags_resolved ON billing_flags(resolved);
CREATE INDEX IF NOT EXISTS idx_client_contracts_client_id ON client_contracts(client_id);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._connection: aiosqlite.Connection | None = None

    async def initialize(self):
        """Create database directory and initialize schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SCHEMA_SQL)
        await self._connection.commit()
        logger.info("Database initialized at %s", self.db_path)

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
