"""Manage to Zero API: zero-target card counts and drill-down ticket lists."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request

from app.api.queries import CLOSED_STATUSES_SQL, PRIORITY_ORDER, get_ticket_url, ticket_row_to_dict

router = APIRouter(prefix="/api", tags=["manage-to-zero"])


@router.get("/manage-to-zero")
async def manage_to_zero(
    request: Request,
    provider: str | None = Query(None, description="Filter by PSA provider"),
    hide_corp: bool = Query(False, description="Exclude Corp-tagged tickets"),
):
    """Get all Manage to Zero card counts."""
    db = request.app.state.db
    conn = await db.get_connection()

    # Provider + Corp filter clauses
    prov_clause = ""
    prov_params: list = []
    if provider:
        prov_clause = " AND provider = ?"
        prov_params = [provider]
    if hide_corp:
        prov_clause += " AND is_corp = 0"

    # Get configurable thresholds
    stale_days_row = await conn.execute_fetchall(
        "SELECT value FROM dashboard_config WHERE key = 'stale_ticket_threshold_days'"
    )
    stale_days = int(stale_days_row[0][0]) if stale_days_row else 3

    sla_warn_row = await conn.execute_fetchall(
        "SELECT value FROM dashboard_config WHERE key = 'sla_warning_minutes'"
    )
    sla_warn_minutes = int(sla_warn_row[0][0]) if sla_warn_row else 30

    now = datetime.now()
    stale_cutoff = (now - timedelta(days=stale_days)).isoformat()
    sla_warn_cutoff = (now + timedelta(minutes=sla_warn_minutes)).isoformat()
    now_iso = now.isoformat()

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

    # Stale tickets (no update in X days)
    stale = await conn.execute_fetchall(
        f"SELECT COUNT(*) FROM tickets WHERE status NOT IN {CLOSED_STATUSES_SQL} AND updated_time < ?{prov_clause}",
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

    return {
        "cards": {
            "unassigned": unassigned[0][0],
            "no_first_response": no_response[0][0],
            "awaiting_tech_reply": awaiting_tech[0][0],
            "stale": stale[0][0],
            "sla_breaching_soon": sla_breaching[0][0],
            "sla_violated": sla_violated[0][0],
            "unresolved_billing_flags": billing_flags[0][0],
        }
    }


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

    # Get thresholds
    stale_days_row = await conn.execute_fetchall(
        "SELECT value FROM dashboard_config WHERE key = 'stale_ticket_threshold_days'"
    )
    stale_days = int(stale_days_row[0][0]) if stale_days_row else 3
    sla_warn_row = await conn.execute_fetchall(
        "SELECT value FROM dashboard_config WHERE key = 'sla_warning_minutes'"
    )
    sla_warn_minutes = int(sla_warn_row[0][0]) if sla_warn_row else 30

    stale_cutoff = (now - timedelta(days=stale_days)).isoformat()
    sla_warn_cutoff = (now + timedelta(minutes=sla_warn_minutes)).isoformat()
    now_iso = now.isoformat()

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
        "sla_violated": f"""
            SELECT * FROM tickets
            WHERE status NOT IN {CLOSED_STATUSES_SQL}
            AND (first_response_violated = 1 OR resolution_violated = 1)
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, created_time ASC
        """,
        "unresolved_billing_flags": f"""
            SELECT t.* FROM tickets t
            JOIN billing_flags bf ON t.id = bf.ticket_id
            WHERE bf.resolved = 0
            {extra}
            ORDER BY {PRIORITY_ORDER} DESC, t.created_time ASC
        """,
    }

    if card_type not in query_map:
        return {"tickets": [], "error": f"Unknown card type: {card_type}"}

    rows = await conn.execute_fetchall(query_map[card_type], params)
    tickets = [ticket_row_to_dict(row) for row in rows]

    # Add ticket URLs
    for t in tickets:
        t["url"] = get_ticket_url(t["id"], request.app.state.providers)

    return {"tickets": tickets, "count": len(tickets)}
