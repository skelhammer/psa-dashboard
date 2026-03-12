"""Post-sync hooks: billing flags, conversation sync, reopened detection.

These run after the main sync commits and operate on SQLite data.
They work identically regardless of which PSA provider ran the sync.
"""

from __future__ import annotations

import logging
from datetime import datetime

import aiosqlite

from app.psa.base import PSAProvider

logger = logging.getLogger(__name__)


async def run_post_sync_hooks(conn: aiosqlite.Connection, provider: PSAProvider):
    """Run all post-sync hooks."""
    await sync_billing_config(conn)
    await generate_billing_flags(conn)
    await sync_conversations_for_open_tickets(conn, provider)


async def sync_billing_config(conn: aiosqlite.Connection):
    """Auto-create/update billing_config for clients with billable contracts.

    Only updates entries where auto_detected = true (never overwrites manual overrides).
    """
    now = datetime.now().isoformat()

    # Find clients with active hourly or block_hour contracts
    rows = await conn.execute_fetchall(
        """SELECT DISTINCT client_id, client_name, contract_type
           FROM client_contracts
           WHERE status = 'active'
             AND contract_type IN ('hourly', 'block_hour')"""
    )

    for row in rows:
        client_id = row[0]
        contract_type = row[2]

        # Check if manual override exists
        existing = await conn.execute_fetchall(
            "SELECT auto_detected FROM billing_config WHERE client_id = ?",
            (client_id,),
        )

        if existing and not existing[0][0]:
            # Manual override exists, skip
            continue

        # Auto-create or update
        await conn.execute(
            """INSERT INTO billing_config (client_id, billing_type, auto_detected, updated_at)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(client_id) DO UPDATE SET
                   billing_type = CASE WHEN auto_detected = 1 THEN excluded.billing_type ELSE billing_type END,
                   updated_at = excluded.updated_at""",
            (client_id, contract_type, now),
        )

    logger.info("Billing config sync complete")


async def generate_billing_flags(conn: aiosqlite.Connection):
    """Generate billing flags for billable client tickets missing worklogs.

    Rules (for clients where track_billing = true):
    - MISSING_WORKLOG: Resolved/Closed, worklog_minutes is 0 or null
    - ZERO_TIME: Has worklog entries but sum to 0 (detected by worklog_minutes = 0 with activity)
    - LOW_TIME: Resolved/Closed and worklog_minutes < minimum_bill_minutes
    """
    now = datetime.now().isoformat()

    # Get billable clients
    billable = await conn.execute_fetchall(
        """SELECT client_id, minimum_bill_minutes
           FROM billing_config
           WHERE track_billing = 1"""
    )

    if not billable:
        return

    for client_id, min_minutes in billable:
        # MISSING_WORKLOG: resolved/closed tickets with 0 worklog
        tickets = await conn.execute_fetchall(
            """SELECT id, display_id, subject
               FROM tickets
               WHERE client_id = ?
                 AND status IN ('Resolved', 'Closed')
                 AND (worklog_minutes IS NULL OR worklog_minutes = 0)""",
            (client_id,),
        )

        for ticket in tickets:
            ticket_id = ticket[0]
            # Check if flag already exists and is unresolved
            existing = await conn.execute_fetchall(
                """SELECT id FROM billing_flags
                   WHERE ticket_id = ? AND flag_type = 'MISSING_WORKLOG' AND resolved = 0""",
                (ticket_id,),
            )
            if not existing:
                await conn.execute(
                    """INSERT INTO billing_flags (ticket_id, flag_type, flag_reason, flagged_at)
                       VALUES (?, 'MISSING_WORKLOG', ?, ?)""",
                    (ticket_id, f"Resolved ticket with no time logged", now),
                )

        # LOW_TIME: resolved/closed tickets with worklog < minimum
        if min_minutes > 0:
            low_tickets = await conn.execute_fetchall(
                """SELECT id, display_id, worklog_minutes
                   FROM tickets
                   WHERE client_id = ?
                     AND status IN ('Resolved', 'Closed')
                     AND worklog_minutes > 0
                     AND worklog_minutes < ?""",
                (client_id, min_minutes),
            )

            for ticket in low_tickets:
                ticket_id = ticket[0]
                logged = ticket[2]
                existing = await conn.execute_fetchall(
                    """SELECT id FROM billing_flags
                       WHERE ticket_id = ? AND flag_type = 'LOW_TIME' AND resolved = 0""",
                    (ticket_id,),
                )
                if not existing:
                    await conn.execute(
                        """INSERT INTO billing_flags (ticket_id, flag_type, flag_reason, flagged_at)
                           VALUES (?, 'LOW_TIME', ?, ?)""",
                        (ticket_id, f"Only {logged} minutes logged (minimum: {min_minutes})", now),
                    )

    # Auto-resolve flags where worklog time has appeared
    await conn.execute(
        """UPDATE billing_flags
           SET resolved = 1, resolved_at = ?, resolution_note = 'Auto-resolved: worklog time added'
           WHERE resolved = 0
             AND flag_type IN ('MISSING_WORKLOG', 'ZERO_TIME')
             AND ticket_id IN (
                 SELECT id FROM tickets WHERE worklog_minutes > 0
             )""",
        (now,),
    )

    logger.info("Billing flag generation complete")


async def sync_conversations_for_open_tickets(conn: aiosqlite.Connection, provider: PSAProvider):
    """Sync conversation data for open tickets to detect awaiting-tech-reply.

    Only syncs conversations for tickets in active statuses to avoid
    expensive bulk conversation fetches.
    """
    import asyncio

    # Get open tickets that need conversation sync
    open_tickets = await conn.execute_fetchall(
        """SELECT id FROM tickets
           WHERE status NOT IN ('Resolved', 'Closed')
           ORDER BY updated_time DESC
           LIMIT 50"""
    )

    if not open_tickets:
        return

    logger.info("Syncing conversations for %d open tickets", len(open_tickets))

    # Batch conversation fetches (concurrent but limited)
    semaphore = asyncio.Semaphore(5)
    unique_types: set[str] = set()

    async def fetch_and_update(ticket_id: str):
        async with semaphore:
            try:
                convos = await provider.get_ticket_conversations(ticket_id)
                if not convos:
                    return

                total_count = len(convos)
                # Count tech replies: REQ_REPLY is requester, everything else is tech
                tech_count = sum(1 for c in convos if c.conv_type != "REQ_REPLY")

                for c in convos:
                    unique_types.add(c.conv_type)

                # Determine last responder
                last_responder = "tech"
                if convos:
                    # Sort by time to find most recent
                    sorted_convos = sorted(
                        [c for c in convos if c.time],
                        key=lambda c: c.time,
                        reverse=True,
                    )
                    if sorted_convos:
                        last = sorted_convos[0]
                        last_responder = "requester" if last.conv_type == "REQ_REPLY" else "tech"
                        last_time = last.time.isoformat() if last.time else None
                    else:
                        last_time = None
                else:
                    last_time = None

                await conn.execute(
                    """UPDATE tickets
                       SET conversation_count = ?, tech_reply_count = ?,
                           last_conversation_time = ?, last_responder_type = ?
                       WHERE id = ?""",
                    (total_count, tech_count, last_time, last_responder, ticket_id),
                )
            except Exception as e:
                logger.warning("Failed to sync conversations for ticket %s: %s", ticket_id, e)

    tasks = [fetch_and_update(row[0]) for row in open_tickets]
    await asyncio.gather(*tasks)

    if unique_types:
        logger.info("=== Discovered conversation types: %s ===", unique_types)
