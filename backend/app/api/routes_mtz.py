"""Manage to Zero API: zero-target card counts, drill-down ticket lists, and trend data."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request

from app.api.queries import CLOSED_STATUSES_SQL, PRIORITY_ORDER, get_ticket_url, ticket_row_to_dict

router = APIRouter(prefix="/api", tags=["manage-to-zero"])


async def _get_mtz_config(conn) -> dict:
    """Load all MTZ-related config from dashboard_config."""
    keys = [
        "stale_ticket_threshold_days",
        "sla_warning_minutes",
        "mtz_yellow_pct",
        "mtz_red_pct",
        "mtz_yellow_floor",
        "mtz_red_floor",
        "stale_exclude_statuses",
    ]
    placeholders = ",".join("?" for _ in keys)
    rows = await conn.execute_fetchall(
        f"SELECT key, value FROM dashboard_config WHERE key IN ({placeholders})",
        keys,
    )
    cfg = {row[0]: row[1] for row in rows}
    return {
        "stale_days": int(cfg.get("stale_ticket_threshold_days", "3")),
        "sla_warn_minutes": int(cfg.get("sla_warning_minutes", "30")),
        "yellow_pct": float(cfg.get("mtz_yellow_pct", "2")),
        "red_pct": float(cfg.get("mtz_red_pct", "5")),
        "yellow_floor": int(cfg.get("mtz_yellow_floor", "2")),
        "red_floor": int(cfg.get("mtz_red_floor", "5")),
        "stale_exclude_statuses": [
            s.strip() for s in cfg.get("stale_exclude_statuses", "").split(",") if s.strip()
        ],
    }


def _build_stale_exclude_sql(statuses: list[str]) -> str:
    """Build SQL clause to exclude wait-statuses from stale count."""
    if not statuses:
        return ""
    escaped = ", ".join(f"'{s}'" for s in statuses)
    return f" AND status NOT IN ({escaped})"


@router.get("/manage-to-zero")
async def manage_to_zero(
    request: Request,
    provider: str | None = Query(None, description="Filter by PSA provider"),
    hide_corp: bool = Query(False, description="Exclude Corp-tagged tickets"),
):
    """Get all Manage to Zero card counts with dynamic thresholds."""
    db = request.app.state.db
    conn = await db.get_connection()

    cfg = await _get_mtz_config(conn)

    # Provider + Corp filter clauses
    prov_clause = ""
    prov_params: list = []
    if provider:
        prov_clause = " AND provider = ?"
        prov_params = [provider]
    if hide_corp:
        prov_clause += " AND is_corp = 0"

    now = datetime.now()
    stale_cutoff = (now - timedelta(days=cfg["stale_days"])).isoformat()
    sla_warn_cutoff = (now + timedelta(minutes=cfg["sla_warn_minutes"])).isoformat()
    now_iso = now.isoformat()

    stale_exclude = _build_stale_exclude_sql(cfg["stale_exclude_statuses"])

    # Total open tickets (for dynamic threshold calculation)
    open_count_row = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL}{prov_clause}",
        prov_params,
    )
    open_count = open_count_row[0][0] if open_count_row else 0

    # Unassigned tickets
    unassigned = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND (technician_id IS NULL OR technician_id = ''){prov_clause}",
        prov_params,
    )

    # No first response
    no_response = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND first_response_time IS NULL{prov_clause}",
        prov_params,
    )

    # Awaiting tech reply (customer replied, tech hasn't)
    awaiting_tech = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND last_responder_type = 'requester'{prov_clause}",
        prov_params,
    )

    # Stale tickets (no update in X days, excluding wait-statuses)
    stale = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND updated_time < ?{stale_exclude}{prov_clause}",
        [stale_cutoff, *prov_params],
    )

    # SLA breaching soon (within warning window, not yet violated)
    sla_breaching = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}{prov_clause}
            AND (
                (first_response_due IS NOT NULL AND first_response_due <= ? AND first_response_due > ? AND (first_response_violated IS NULL OR first_response_violated = 0))
                OR
                (resolution_due IS NOT NULL AND resolution_due <= ? AND resolution_due > ? AND (resolution_violated IS NULL OR resolution_violated = 0))
            )""",
        [*prov_params, sla_warn_cutoff, now_iso, sla_warn_cutoff, now_iso],
    )

    # SLA already violated (still open)
    sla_violated = await conn.execute_fetchall(
        f"""SELECT COUNT(*) FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}{prov_clause}
            AND (first_response_violated = 1 OR resolution_violated = 1)""",
        prov_params,
    )

    # Reopened tickets (still open)
    reopened = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND reopened = 1{prov_clause}",
        prov_params,
    )

    # Unresolved billing flags (join with tickets for provider filtering)
    if provider:
        billing_flags = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM billing_flags bf JOIN tickets t ON bf.ticket_id = t.id WHERE bf.resolved = 0 AND t.provider = ?",
            [provider],
        )
    else:
        billing_flags = await conn.execute_fetchall(
            "SELECT COUNT(*) FROM billing_flags WHERE resolved = 0"
        )

    # Calculate dynamic thresholds based on open ticket volume
    yellow_threshold = max(cfg["yellow_floor"], int(open_count * cfg["yellow_pct"] / 100))
    red_threshold = max(cfg["red_floor"], int(open_count * cfg["red_pct"] / 100))

    return {
        "cards": {
            "unassigned": unassigned[0][0],
            "no_first_response": no_response[0][0],
            "awaiting_tech_reply": awaiting_tech[0][0],
            "stale": stale[0][0],
            "sla_breaching_soon": sla_breaching[0][0],
            "open_violations": sla_violated[0][0],
            "reopened": reopened[0][0],
            "unresolved_billing_flags": billing_flags[0][0],
        },
        "thresholds": {
            "yellow": yellow_threshold,
            "red": red_threshold,
        },
        "open_count": open_count,
    }


@router.get("/manage-to-zero/trends")
async def mtz_trends(
    request: Request,
    hours: int = Query(8, description="Hours of trend data to return"),
):
    """Get MTZ card count history for sparklines."""
    db = request.app.state.db
    conn = await db.get_connection()

    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    rows = await conn.execute_fetchall(
        "SELECT recorded_at, card_key, count FROM mtz_snapshots WHERE recorded_at >= ? ORDER BY recorded_at ASC",
        [cutoff],
    )

    # Group by card_key
    trends: dict[str, list[dict]] = {}
    for row in rows:
        key = row[1]
        if key not in trends:
            trends[key] = []
        trends[key].append({"time": row[0], "count": row[2]})

    return {"trends": trends}


@router.get("/manage-to-zero/{card_type}")
async def mtz_drilldown(
    card_type: str,
    request: Request,
    client_id: str | None = Query(None),
    technician_id: str | None = Query(None),
    provider: str | None = Query(None),
    hide_corp: bool = Query(False),
):
    """Get ticket list for a specific MTZ card type."""
    db = request.app.state.db
    conn = await db.get_connection()

    cfg = await _get_mtz_config(conn)
    now = datetime.now()
    extra_filters = []
    params: list = []

    if client_id:
        extra_filters.append("AND client_id = ?")
        params.append(client_id)
    if technician_id:
        extra_filters.append("AND technician_id = ?")
        params.append(technician_id)
    if provider:
        extra_filters.append("AND provider = ?")
        params.append(provider)
    if hide_corp:
        extra_filters.append("AND is_corp = 0")

    extra = " ".join(extra_filters)

    stale_cutoff = (now - timedelta(days=cfg["stale_days"])).isoformat()
    sla_warn_cutoff = (now + timedelta(minutes=cfg["sla_warn_minutes"])).isoformat()
    now_iso = now.isoformat()
    stale_exclude = _build_stale_exclude_sql(cfg["stale_exclude_statuses"])

    query_map = {
        "unassigned": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND (technician_id IS NULL OR technician_id = '')
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, first_response_due ASC
        """,
        "no_first_response": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND first_response_time IS NULL
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, first_response_due ASC
        """,
        "awaiting_tech_reply": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND last_responder_type = 'requester'
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, last_conversation_time ASC
        """,
        "stale": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND updated_time < '{stale_cutoff}'
            {stale_exclude}
            {extra}
            ORDER BY updated_time ASC
        """,
        "sla_breaching_soon": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND (
                (first_response_due IS NOT NULL AND first_response_due <= '{sla_warn_cutoff}' AND first_response_due > '{now_iso}' AND (first_response_violated IS NULL OR first_response_violated = 0))
                OR
                (resolution_due IS NOT NULL AND resolution_due <= '{sla_warn_cutoff}' AND resolution_due > '{now_iso}' AND (resolution_violated IS NULL OR resolution_violated = 0))
            )
            {extra}
            ORDER BY COALESCE(first_response_due, resolution_due) ASC
        """,
        "open_violations": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND (first_response_violated = 1 OR resolution_violated = 1)
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, created_time ASC
        """,
        "reopened": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND reopened = 1
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, updated_time DESC
        """,
        "unresolved_billing_flags": f"""
            SELECT t.* FROM tickets t
            JOIN billing_flags bf ON t.id = bf.ticket_id
            WHERE bf.resolved = 0
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, t.created_time ASC
        """,
    }

    # Backward compat: accept old key name
    if card_type == "sla_violated":
        card_type = "open_violations"

    if card_type not in query_map:
        return {"tickets": [], "error": f"Unknown card type: {card_type}"}

    rows = await conn.execute_fetchall(query_map[card_type], params)
    tickets = [ticket_row_to_dict(row) for row in rows]

    # Add ticket URLs
    for t in tickets:
        t["url"] = get_ticket_url(t["id"], request.app.state.providers)

    return {"tickets": tickets, "count": len(tickets)}


async def record_mtz_snapshot(conn):
    """Record current MTZ card counts for trend tracking.

    Call this after each sync cycle completes.
    """
    from app.api.queries import CLOSED_STATUSES_SQL

    now = datetime.now()
    now_iso = now.isoformat()

    cfg = await _get_mtz_config(conn)
    stale_cutoff = (now - timedelta(days=cfg["stale_days"])).isoformat()
    sla_warn_cutoff = (now + timedelta(minutes=cfg["sla_warn_minutes"])).isoformat()
    stale_exclude = _build_stale_exclude_sql(cfg["stale_exclude_statuses"])

    queries = {
        "unassigned": f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND (technician_id IS NULL OR technician_id = '')",
        "no_first_response": f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND first_response_time IS NULL",
        "awaiting_tech_reply": f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND last_responder_type = 'requester'",
        "stale": f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND updated_time < '{stale_cutoff}'{stale_exclude}",
        "sla_breaching_soon": f"""SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND ((first_response_due IS NOT NULL AND first_response_due <= '{sla_warn_cutoff}' AND first_response_due > '{now_iso}' AND (first_response_violated IS NULL OR first_response_violated = 0))
            OR (resolution_due IS NOT NULL AND resolution_due <= '{sla_warn_cutoff}' AND resolution_due > '{now_iso}' AND (resolution_violated IS NULL OR resolution_violated = 0)))""",
        "open_violations": f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND (first_response_violated = 1 OR resolution_violated = 1)",
        "reopened": f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND reopened = 1",
    }

    for card_key, query in queries.items():
        row = await conn.execute_fetchall(query)
        count = row[0][0] if row else 0
        await conn.execute(
            "INSERT INTO mtz_snapshots (recorded_at, card_key, count) VALUES (?, ?, ?)",
            [now_iso, card_key, count],
        )

    # Prune old snapshots (keep 48 hours)
    prune_cutoff = (now - timedelta(hours=48)).isoformat()
    await conn.execute("DELETE FROM mtz_snapshots WHERE recorded_at < ?", [prune_cutoff])

    await conn.commit()
