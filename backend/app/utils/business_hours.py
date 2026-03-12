"""Business hours calculator.

Calculates elapsed minutes between two datetimes counting only
minutes that fall within configured business hours on work days.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta


def calculate_business_minutes(
    start: datetime,
    end: datetime,
    config,
) -> float:
    """Return the number of business-hour minutes between *start* and *end*.

    Parameters
    ----------
    start, end : datetime
        Naive or aware datetimes. Timezone info is stripped before calculation.
    config : object
        Must expose ``start_hour`` (int), ``end_hour`` (int),
        ``work_days`` (list[int], 1=Mon..7=Sun), and
        ``holidays`` (list[str] of ISO date strings like "2026-01-01").

    Returns
    -------
    float
        Elapsed business minutes (>= 0).
    """
    if end <= start:
        return 0.0

    bh_start = config.start_hour
    bh_end = config.end_hour
    work_days: set[int] = set(config.work_days)
    holidays: set[date] = {
        date.fromisoformat(h) for h in (config.holidays or [])
    }
    minutes_per_day = (bh_end - bh_start) * 60

    # Strip timezone info for consistent arithmetic
    s = start.replace(tzinfo=None)
    e = end.replace(tzinfo=None)

    def _is_work_day(d: date) -> bool:
        return d.isoweekday() in work_days and d not in holidays

    def _clamp_to_bh(dt: datetime) -> datetime:
        """Clamp a datetime into the business-hours window of its day."""
        day_start = dt.replace(hour=bh_start, minute=0, second=0, microsecond=0)
        day_end = dt.replace(hour=bh_end, minute=0, second=0, microsecond=0)
        if dt < day_start:
            return day_start
        if dt > day_end:
            return day_end
        return dt

    # Same calendar day
    if s.date() == e.date():
        if not _is_work_day(s.date()):
            return 0.0
        cs = _clamp_to_bh(s)
        ce = _clamp_to_bh(e)
        diff = (ce - cs).total_seconds() / 60
        return max(diff, 0.0)

    total = 0.0

    # Minutes remaining on the start day
    if _is_work_day(s.date()):
        cs = _clamp_to_bh(s)
        day_end = s.replace(hour=bh_end, minute=0, second=0, microsecond=0)
        diff = (day_end - cs).total_seconds() / 60
        total += max(diff, 0.0)

    # Minutes used on the end day
    if _is_work_day(e.date()):
        ce = _clamp_to_bh(e)
        day_start = e.replace(hour=bh_start, minute=0, second=0, microsecond=0)
        diff = (ce - day_start).total_seconds() / 60
        total += max(diff, 0.0)

    # Full business days in between (exclusive of start and end dates)
    # For efficiency, count calendar days then subtract non-work days.
    next_day = s.date() + timedelta(days=1)
    end_date = e.date()

    if next_day < end_date:
        span_days = (end_date - next_day).days  # number of days in [next_day, end_date)
        # Count full weeks and remainder
        full_weeks, remainder = divmod(span_days, 7)

        # Business days in a full week
        biz_per_week = sum(1 for wd in range(1, 8) if wd in work_days)
        full_biz_days = full_weeks * biz_per_week

        # Remainder days
        remainder_biz = 0
        for i in range(remainder):
            d = next_day + timedelta(days=full_weeks * 7 + i)
            if d.isoweekday() in work_days:
                remainder_biz += 1

        # Subtract holidays that fall within the range
        holiday_count = sum(
            1 for h in holidays
            if next_day <= h < end_date and h.isoweekday() in work_days
        )

        total += (full_biz_days + remainder_biz - holiday_count) * minutes_per_day

    return total
