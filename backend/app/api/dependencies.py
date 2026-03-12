"""Shared API dependencies: database access, common filter parameters."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Query


class FilterParams:
    """Common filter parameters parsed from query string."""

    def __init__(
        self,
        date_range: str = Query("this_month", description="Preset date range"),
        date_from: str | None = Query(None, description="Custom start date (ISO format)"),
        date_to: str | None = Query(None, description="Custom end date (ISO format)"),
        client_id: str | None = Query(None),
        technician_id: str | None = Query(None),
        priority: str | None = Query(None),
        status: str | None = Query(None),
        category: str | None = Query(None),
    ):
        self.client_id = client_id
        self.technician_id = technician_id
        self.priority = priority
        self.status = status
        self.category = category

        # Resolve date range
        now = datetime.now()
        if date_from and date_to:
            self.date_from = datetime.fromisoformat(date_from)
            self.date_to = datetime.fromisoformat(date_to)
        else:
            self.date_from, self.date_to = self._resolve_date_range(date_range, now)

    @staticmethod
    def _resolve_date_range(preset: str, now: datetime) -> tuple[datetime, datetime]:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        match preset:
            case "today":
                return today_start, now
            case "this_week":
                weekday = now.weekday()
                week_start = today_start - timedelta(days=weekday)
                return week_start, now
            case "this_month":
                month_start = today_start.replace(day=1)
                return month_start, now
            case "this_quarter":
                quarter_month = ((now.month - 1) // 3) * 3 + 1
                quarter_start = today_start.replace(month=quarter_month, day=1)
                return quarter_start, now
            case "this_year":
                year_start = today_start.replace(month=1, day=1)
                return year_start, now
            case "last_30":
                return today_start - timedelta(days=30), now
            case "last_90":
                return today_start - timedelta(days=90), now
            case _:
                month_start = today_start.replace(day=1)
                return month_start, now


def build_where_clause(filters: FilterParams, prefix: str = "", include_date: bool = True) -> tuple[str, list]:
    """Build SQL WHERE conditions from filter params.

    Returns (where_clause, params) where where_clause includes 'WHERE' if non-empty.
    """
    conditions = []
    params = []
    col_prefix = f"{prefix}." if prefix else ""

    if include_date and filters.date_from:
        conditions.append(f"{col_prefix}created_time >= ?")
        params.append(filters.date_from.isoformat())
    if include_date and filters.date_to:
        conditions.append(f"{col_prefix}created_time <= ?")
        params.append(filters.date_to.isoformat())
    if filters.client_id:
        conditions.append(f"{col_prefix}client_id = ?")
        params.append(filters.client_id)
    if filters.technician_id:
        conditions.append(f"{col_prefix}technician_id = ?")
        params.append(filters.technician_id)
    if filters.priority:
        conditions.append(f"{col_prefix}priority = ?")
        params.append(filters.priority)
    if filters.status:
        conditions.append(f"{col_prefix}status = ?")
        params.append(filters.status)
    if filters.category:
        conditions.append(f"{col_prefix}category = ?")
        params.append(filters.category)

    if conditions:
        return "WHERE " + " AND ".join(conditions), params
    return "", params
