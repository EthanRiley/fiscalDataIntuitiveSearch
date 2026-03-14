"""Utilities for processing fiscal data records before analysis."""

import math
from datetime import datetime


def _period_key(date_str: str, periodicity: str) -> str:
    """Return a grouping key for a date string based on the given periodicity."""
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return date_str

    if periodicity == "decade":
        return str(math.floor(dt.year / 10) * 10)
    if periodicity == "year":
        return str(dt.year)
    if periodicity == "month":
        return dt.strftime("%Y-%m")
    if periodicity == "week":
        return dt.strftime("%Y-W%W")
    # day — passthrough
    return dt.strftime("%Y-%m-%d")


def filter_by_periodicity(records: list[dict], date_column: str, periodicity: str) -> list[dict]:
    """
    Reduce records to one entry per time period.

    Records are assumed to be sorted ascending by date. The last record
    in each period group is kept (most recent within that period).

    Args:
        records:     List of record dicts from the Fiscal Data API.
        date_column: The field name containing the date string.
        periodicity: One of 'decade', 'year', 'month', 'week', 'day'.

    Returns:
        Filtered list with one record per period, in ascending order.
    """
    if not records or periodicity == "day":
        return records

    seen: dict[str, dict] = {}
    for record in records:
        key = _period_key(record.get(date_column, ""), periodicity)
        seen[key] = record  # later record overwrites — keeps last in each period

    return list(seen.values())
