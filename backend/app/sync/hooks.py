"""Post-sync hooks: billing flags, conversation sync, reopened detection.

These run after the main sync commits and operate on SQLite data.

Each hook that mutates provider-specific rows (tickets, clients, contracts,
billing_config, billing_flags) accepts the syncing provider's name and scopes
its queries accordingly, so a SuperOps sync never touches Zendesk rows and
vice-versa. Hooks whose output is a cross-provider rollup (MTZ snapshots)
stay unscoped by design.

Passing provider_name="" (the default) preserves the legacy global behavior
for ad-hoc/CLI invocations that do not know the provider.
"""

from __future__ import annotations

import logging
from datetime import datetime

import aiosqlite

from app.api.queries import get_closed_statuses_sql
from app.psa.base import PSAProvider

logger = logging.getLogger(__name__)


def _provider_filter(provider_name: str, column: str = "provider") -> tuple[str, list]:
    """Build an optional provider-scoping SQL fragment.

    Returns ("", []) when provider_name is empty so the caller can inline
    the result without conditionals.
    """
    if not provider_name:
        return "", []
    return f" AND {column} = ?", [provider_name]


async def run_post_sync_hooks(
    conn: aiosqlite.Connection, provider: PSAProvider, provider_name: str = ""
):
    """Run all post-sync hooks, scoped to the syncing provider."""
    await backfill_resolution_time(conn, provider_name)
    await sync_billing_config(conn, provider_name)
    await generate_billing_flags(conn, provider_name)
    await sync_conversations_for_open_tickets(conn, provider, provider_name)
    await record_mtz_snapshots(conn)


async def backfill_resolution_time(conn: aiosqlite.Connection, provider_name: str = ""):
    """Backfill resolution_time from updated_time for closed tickets missing it.

    Old imported tickets often lack resolution_time. Using updated_time as a
    fallback keeps closed-ticket queries accurate without COALESCE everywhere.
    """
    closed = get_closed_statuses_sql()
    provider_clause, provider_params = _provider_filter(provider_name)
    result = await conn.execute(
        f"""UPDATE tickets SET resolution_time = updated_time
           WHERE status IN {closed}
             AND resolution_time IS NULL
             AND updated_time IS NOT NULL{provider_clause}""",
        provider_params,
    )
    if result.rowcount:
        logger.info("Backfilled resolution_time for %d closed tickets", result.rowcount)


async def sync_billing_config(conn: aiosqlite.Connection, provider_name: str = ""):
    """Auto-create/update billing_config for clients based on contract whitelist.

    All active clients are treated as hourly (billable) by default. Clients with
    an active contract name or client plan field matching unlimited_plans are
    excluded from billing.

    Only updates entries where auto_detected = true (never overwrites manual overrides).
    """
    from app.config import get_settings
    settings = get_settings()
    unlimited_plans = settings.billing.unlimited_plans
    now = datetime.now().isoformat()
    provider_clause, provider_params = _provider_filter(provider_name)

    # Build set of client IDs on unlimited plans (scoped to this provider)
    excluded_ids: set[str] = set()
    if unlimited_plans:
        placeholders = ",".join("?" for _ in unlimited_plans)

        # Check contract_name first
        contract_rows = await conn.execute_fetchall(
            f"""SELECT DISTINCT client_id FROM client_contracts
                WHERE status = 'active' AND contract_name IN ({placeholders})
                {provider_clause}""",
            [*unlimited_plans, *provider_params],
        )
        excluded_ids.update(row[0] for row in contract_rows)

        # Fall back to clients.plan custom field for clients not already excluded
        plan_rows = await conn.execute_fetchall(
            f"""SELECT id FROM clients
                WHERE stage = 'Active' AND plan IN ({placeholders})
                {provider_clause}""",
            [*unlimited_plans, *provider_params],
        )
        excluded_ids.update(row[0] for row in plan_rows)

        logger.info(
            "Billing exclusion: %d clients on unlimited plans (%d by contract, %d by plan field)",
            len(excluded_ids), len(contract_rows), len(plan_rows),
        )

    # Remove auto-detected billing config for excluded clients
    if excluded_ids:
        id_placeholders = ",".join("?" for _ in excluded_ids)
        await conn.execute(
            f"DELETE FROM billing_config WHERE client_id IN ({id_placeholders}) AND auto_detected = 1",
            list(excluded_ids),
        )
        # Auto-resolve any open billing flags for excluded clients
        await conn.execute(
            f"""UPDATE billing_flags
                SET resolved = 1, resolved_at = ?, resolution_note = 'Auto-resolved: client on unlimited plan'
                WHERE resolved = 0
                  AND ticket_id IN (
                      SELECT id FROM tickets WHERE client_id IN ({id_placeholders})
                  )""",
            [now, *list(excluded_ids)],
        )

    # All other active clients are billable (hourly)
    all_active = await conn.execute_fetchall(
        f"SELECT id FROM clients WHERE stage = 'Active'{provider_clause}",
        provider_params,
    )
    billable_clients = [(row[0], "hourly") for row in all_active if row[0] not in excluded_ids]
    logger.info("Billing: %d active clients are billable, %d excluded (unlimited)", len(billable_clients), len(excluded_ids))

    for client_id, billing_type in billable_clients:
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
            (client_id, billing_type, now),
        )

    logger.info("Billing config sync complete")


async def generate_billing_flags(conn: aiosqlite.Connection, provider_name: str = ""):
    """Generate billing flags for billable client tickets missing worklogs.

    Rules (for clients where track_billing = true):
    - MISSING_WORKLOG: Resolved/Closed, worklog_hours is 0 or null
    - ZERO_TIME: Has worklog entries but sum to 0 (detected by worklog_hours = 0 with activity)
    - LOW_TIME: Resolved/Closed and worklog_hours < minimum_bill_minutes

    Tickets created before billing.flags_start_date (config) are excluded.
    """
    from app.config import get_settings
    settings = get_settings()
    now = datetime.now().isoformat()
    provider_clause, provider_params = _provider_filter(provider_name)
    # When the query aliases `tickets` as `t` we need `t.provider`, not bare `provider`.
    t_provider_clause, _ = _provider_filter(provider_name, column="t.provider")

    # Date cutoff: only flag tickets created on or after this date
    flags_start = settings.billing.flags_start_date
    date_cutoff_sql = ""
    date_cutoff_params: list = []
    if flags_start:
        date_cutoff_sql = " AND created_time >= ?"
        date_cutoff_params = [flags_start]
        # Auto-resolve any existing unresolved flags for tickets before the cutoff
        await conn.execute(
            f"""UPDATE billing_flags
               SET resolved = 1, resolved_at = ?, resolution_note = 'Auto-resolved: ticket before billing start date'
               WHERE resolved = 0
                 AND ticket_id IN (
                     SELECT id FROM tickets WHERE created_time < ?{provider_clause}
                 )""",
            [now, flags_start, *provider_params],
        )

    # Get billable clients scoped to this provider. billing_config has no
    # provider column, so we join through clients.
    if provider_name:
        billable = await conn.execute_fetchall(
            """SELECT bc.client_id, bc.minimum_bill_minutes
               FROM billing_config bc
               JOIN clients c ON bc.client_id = c.id
               WHERE bc.track_billing = 1 AND c.provider = ?""",
            [provider_name],
        )
    else:
        billable = await conn.execute_fetchall(
            """SELECT client_id, minimum_bill_minutes
               FROM billing_config
               WHERE track_billing = 1"""
        )

    if not billable:
        return

    for client_id, min_minutes in billable:
        min_hours = min_minutes / 60  # Convert config (minutes) to hours for comparison

        # MISSING_WORKLOG: resolved/closed tickets with 0 worklog
        closed = get_closed_statuses_sql()
        tickets = await conn.execute_fetchall(
            f"""SELECT id, display_id, subject
               FROM tickets
               WHERE client_id = ?
                 AND status IN {closed}
                 AND (worklog_hours IS NULL OR worklog_hours = 0){date_cutoff_sql}""",
            [client_id, *date_cutoff_params],
        )

        for ticket in tickets:
            ticket_id = ticket[0]
            # Check if flag already exists (resolved or not)
            existing = await conn.execute_fetchall(
                """SELECT id FROM billing_flags
                   WHERE ticket_id = ? AND flag_type = 'MISSING_WORKLOG'""",
                (ticket_id,),
            )
            if not existing:
                await conn.execute(
                    """INSERT INTO billing_flags (ticket_id, flag_type, flag_reason, flagged_at)
                       VALUES (?, 'MISSING_WORKLOG', ?, ?)""",
                    (ticket_id, f"Resolved ticket with no time logged", now),
                )

        # LOW_TIME: resolved/closed tickets with worklog < minimum
        if min_hours > 0:
            low_tickets = await conn.execute_fetchall(
                f"""SELECT id, display_id, worklog_hours
                   FROM tickets
                   WHERE client_id = ?
                     AND status IN {closed}
                     AND worklog_hours > 0
                     AND worklog_hours < ?{date_cutoff_sql}""",
                [client_id, min_hours, *date_cutoff_params],
            )

            for ticket in low_tickets:
                ticket_id = ticket[0]
                logged = ticket[2]
                existing = await conn.execute_fetchall(
                    """SELECT id FROM billing_flags
                       WHERE ticket_id = ? AND flag_type = 'LOW_TIME'""",
                    (ticket_id,),
                )
                if not existing:
                    await conn.execute(
                        """INSERT INTO billing_flags (ticket_id, flag_type, flag_reason, flagged_at)
                           VALUES (?, 'LOW_TIME', ?, ?)""",
                        (ticket_id, f"Only {logged}h logged (minimum: {min_minutes}min)", now),
                    )

    # Auto-resolve flags where worklog time has appeared (scoped to this provider)
    await conn.execute(
        f"""UPDATE billing_flags
           SET resolved = 1, resolved_at = ?, resolution_note = 'Auto-resolved: worklog time added'
           WHERE resolved = 0
             AND flag_type IN ('MISSING_WORKLOG', 'ZERO_TIME')
             AND ticket_id IN (
                 SELECT id FROM tickets WHERE worklog_hours > 0{provider_clause}
             )""",
        [now, *provider_params],
    )

    # Auto-resolve LOW_TIME flags where worklog now meets the minimum
    await conn.execute(
        f"""UPDATE billing_flags
           SET resolved = 1, resolved_at = ?, resolution_note = 'Auto-resolved: worklog time updated above minimum'
           WHERE resolved = 0
             AND flag_type = 'LOW_TIME'
             AND ticket_id IN (
                 SELECT t.id FROM tickets t
                 JOIN billing_config bc ON t.client_id = bc.client_id
                 WHERE t.worklog_hours >= (bc.minimum_bill_minutes / 60.0){t_provider_clause}
             )""",
        [now, *provider_params],
    )

    # Update stale LOW_TIME flag reasons to reflect current worklog
    if provider_name:
        await conn.execute(
            """UPDATE billing_flags
               SET flag_reason = 'Only ' || (
                   SELECT t.worklog_hours FROM tickets t WHERE t.id = billing_flags.ticket_id
               ) || 'h logged (minimum: ' || (
                   SELECT bc.minimum_bill_minutes FROM tickets t2
                   JOIN billing_config bc ON t2.client_id = bc.client_id
                   WHERE t2.id = billing_flags.ticket_id
               ) || 'min)'
               WHERE resolved = 0
                 AND flag_type = 'LOW_TIME'
                 AND ticket_id IN (SELECT id FROM tickets WHERE provider = ?)""",
            [provider_name],
        )
    else:
        await conn.execute(
            """UPDATE billing_flags
               SET flag_reason = 'Only ' || (
                   SELECT t.worklog_hours FROM tickets t WHERE t.id = billing_flags.ticket_id
               ) || 'h logged (minimum: ' || (
                   SELECT bc.minimum_bill_minutes FROM tickets t2
                   JOIN billing_config bc ON t2.client_id = bc.client_id
                   WHERE t2.id = billing_flags.ticket_id
               ) || 'min)'
               WHERE resolved = 0 AND flag_type = 'LOW_TIME'"""
        )

    logger.info("Billing flag generation complete")


async def sync_conversations_for_open_tickets(
    conn: aiosqlite.Connection, provider: PSAProvider, provider_name: str = "",
):
    """Sync conversation data for open tickets to detect awaiting-tech-reply.

    Only syncs conversations for tickets owned by the current provider
    in active statuses, to avoid calling the wrong API.

    Capped per sync to limit external API call volume. Prioritizes tickets
    where the ticket has been updated since the last conversation pull
    (or has never had one), so newly active tickets are picked up first
    and idle ones rotate through over multiple syncs.
    """
    import asyncio

    # Cap how many conversation API calls we make per sync. With one call
    # per ticket and a 15-min sync cadence, 25 gives comfortable headroom
    # for busy mornings while staying well under PSA rate limits.
    MAX_CONVERSATION_FETCHES = 25

    # Order: tickets whose updated_time is newer than last_conversation_time
    # (or which have never been pulled) come first, then by recency.
    closed = get_closed_statuses_sql()
    base_sql = f"""
        SELECT id FROM tickets
        WHERE status NOT IN {closed}
          {{provider_filter}}
        ORDER BY
            CASE
                WHEN last_conversation_time IS NULL THEN 0
                WHEN updated_time > last_conversation_time THEN 0
                ELSE 1
            END,
            updated_time DESC
        LIMIT ?
    """

    if provider_name:
        open_tickets = await conn.execute_fetchall(
            base_sql.format(provider_filter="AND provider = ?"),
            (provider_name, MAX_CONVERSATION_FETCHES),
        )
    else:
        open_tickets = await conn.execute_fetchall(
            base_sql.format(provider_filter=""),
            (MAX_CONVERSATION_FETCHES,),
        )

    if not open_tickets:
        return

    logger.info(
        "Syncing conversations for %d open tickets (cap=%d)",
        len(open_tickets), MAX_CONVERSATION_FETCHES,
    )

    # Batch conversation fetches (concurrent but limited)
    semaphore = asyncio.Semaphore(5)
    unique_types: set[str] = set()

    async def fetch_and_update(ticket_id: str):
        async with semaphore:
            try:
                # Strip provider prefix before calling the API
                native_id = ticket_id.split(":", 1)[1] if ":" in ticket_id else ticket_id
                convos = await provider.get_ticket_conversations(native_id)
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


async def record_mtz_snapshots(conn: aiosqlite.Connection):
    """Record MTZ card counts for trend sparklines.

    MTZ is a cross-provider rollup by design, so this hook stays unscoped.
    """
    try:
        from app.api.routes_mtz import record_mtz_snapshot
        await record_mtz_snapshot(conn)
        logger.info("MTZ trend snapshot recorded")
    except Exception as e:
        logger.warning("Failed to record MTZ snapshot: %s", e)
