"""Reusable SQL query helpers."""

from __future__ import annotations

from app.config import get_settings

PRIORITY_ORDER = """
CASE priority
    WHEN 'Critical' THEN 5
    WHEN 'Urgent' THEN 5
    WHEN 'High' THEN 4
    WHEN 'Medium' THEN 3
    WHEN 'Low' THEN 2
    WHEN 'Very Low' THEN 1
    ELSE 0
END
"""


def _build_closed_statuses_sql() -> str:
    statuses = get_settings().server.closed_statuses
    return "(" + ", ".join(f"'{s}'" for s in statuses) + ")"


# Built at import time from config
CLOSED_STATUSES_SQL = _build_closed_statuses_sql()


def ticket_row_to_dict(row) -> dict:
    """Convert a SQLite Row to a ticket dict for API response."""
    return {
        "id": row["id"],
        "display_id": row["display_id"],
        "subject": row["subject"],
        "ticket_type": row["ticket_type"],
        "source": row["source"],
        "client_id": row["client_id"],
        "client_name": row["client_name"],
        "technician_id": row["technician_id"],
        "technician_name": row["technician_name"],
        "status": row["status"],
        "priority": row["priority"],
        "category": row["category"],
        "subcategory": row["subcategory"],
        "sla_name": row["sla_name"],
        "created_time": row["created_time"],
        "updated_time": row["updated_time"],
        "first_response_due": row["first_response_due"],
        "first_response_time": row["first_response_time"],
        "first_response_violated": bool(row["first_response_violated"]) if row["first_response_violated"] is not None else None,
        "resolution_due": row["resolution_due"],
        "resolution_time": row["resolution_time"],
        "resolution_violated": bool(row["resolution_violated"]) if row["resolution_violated"] is not None else None,
        "worklog_minutes": row["worklog_minutes"],
        "conversation_count": row["conversation_count"],
        "tech_reply_count": row["tech_reply_count"],
        "last_conversation_time": row["last_conversation_time"],
        "last_responder_type": row["last_responder_type"],
        "reopened": bool(row["reopened"]),
    }
