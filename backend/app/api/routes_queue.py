"""Work Queue API: scored/ranked ticket list."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request

from app.api.queries import OPEN_STATUSES_SQL, PRIORITY_ORDER, ticket_row_to_dict

router = APIRouter(prefix="/api", tags=["work-queue"])


async def _get_config_weights(conn) -> dict:
    """Load work queue weights from dashboard_config."""
    rows = await conn.execute_fetchall(
        "SELECT key, value FROM dashboard_config WHERE key LIKE 'work_queue_%'"
    )
    defaults = {
        "work_queue_sla_violated_weight": 1000,
        "work_queue_sla_30min_weight": 500,
        "work_queue_sla_2hr_weight": 200,
        "work_queue_sla_safe_weight": 0,
        "work_queue_priority_critical_weight": 100,
        "work_queue_priority_high_weight": 75,
        "work_queue_priority_medium_weight": 50,
        "work_queue_priority_low_weight": 25,
        "work_queue_age_weight_per_hour": 1,
    }
    for row in rows:
        defaults[row["key"]] = int(row["value"])
    return defaults


def _compute_score(ticket: dict, weights: dict, now: datetime) -> float:
    """Compute ranking score for a ticket."""
    score = 0.0

    # SLA urgency score
    fr_violated = ticket.get("first_response_violated")
    res_violated = ticket.get("resolution_violated")

    if fr_violated or res_violated:
        score += weights["work_queue_sla_violated_weight"]
    else:
        # Check time remaining until SLA breach
        fr_due = ticket.get("first_response_due")
        res_due = ticket.get("resolution_due")

        min_remaining = None
        for due_str in [fr_due, res_due]:
            if due_str:
                try:
                    due_dt = datetime.fromisoformat(due_str)
                    remaining = (due_dt - now).total_seconds() / 60  # minutes
                    if min_remaining is None or remaining < min_remaining:
                        min_remaining = remaining
                except (ValueError, TypeError):
                    pass

        if min_remaining is not None:
            if min_remaining <= 0:
                score += weights["work_queue_sla_violated_weight"]
            elif min_remaining <= 30:
                score += weights["work_queue_sla_30min_weight"]
            elif min_remaining <= 120:
                score += weights["work_queue_sla_2hr_weight"]
            else:
                score += weights["work_queue_sla_safe_weight"]

    # Priority score
    priority = ticket.get("priority", "Medium")
    priority_map = {
        "Critical": weights["work_queue_priority_critical_weight"],
        "Urgent": weights["work_queue_priority_critical_weight"],
        "High": weights["work_queue_priority_high_weight"],
        "Medium": weights["work_queue_priority_medium_weight"],
        "Low": weights["work_queue_priority_low_weight"],
        "Very Low": weights["work_queue_priority_low_weight"],
    }
    score += priority_map.get(priority, weights["work_queue_priority_medium_weight"])

    # Age bonus (1 point per hour old)
    created = ticket.get("created_time")
    if created:
        try:
            created_dt = datetime.fromisoformat(created)
            age_hours = (now - created_dt).total_seconds() / 3600
            score += age_hours * weights["work_queue_age_weight_per_hour"]
        except (ValueError, TypeError):
            pass

    return score


@router.get("/work-queue")
async def work_queue(
    request: Request,
    client_id: str | None = Query(None),
    technician_id: str | None = Query(None),
    priority: str | None = Query(None),
    status: str | None = Query(None),
    tech_group: str | None = Query(None),
    unassigned_only: bool = Query(False),
):
    """Get prioritized work queue of open tickets."""
    db = request.app.state.db
    conn = await db.get_connection()

    conditions = [f"status IN {OPEN_STATUSES_SQL}"]
    params: list = []

    if client_id:
        conditions.append("client_id = ?")
        params.append(client_id)
    if technician_id:
        conditions.append("technician_id = ?")
        params.append(technician_id)
    if priority:
        conditions.append("priority = ?")
        params.append(priority)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if tech_group:
        conditions.append("COALESCE(tech_group_name, 'Tier 1 Support') = ?")
        params.append(tech_group)
    if unassigned_only:
        conditions.append("(technician_id IS NULL OR technician_id = '')")

    where = " AND ".join(conditions)

    rows = await conn.execute_fetchall(
        f"SELECT * FROM tickets WHERE {where}",
        params,
    )

    tickets = [ticket_row_to_dict(row) for row in rows]

    # Compute scores and rank
    weights = await _get_config_weights(conn)
    now = datetime.now()

    for ticket in tickets:
        ticket["score"] = _compute_score(ticket, weights, now)
        ticket["url"] = request.app.state.provider.get_ticket_url(ticket["id"])

    # Sort by score descending
    tickets.sort(key=lambda t: t["score"], reverse=True)

    # Add rank
    for i, ticket in enumerate(tickets, 1):
        ticket["rank"] = i

    return {"tickets": tickets, "count": len(tickets)}
