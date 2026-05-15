"""Display formatting helpers shared across pages.

Centralizes date, time, money, and similar display conversions so
the same value renders consistently everywhere in the app.
"""

from datetime import date, datetime
from typing import Optional, Union


def format_date(value: Optional[Union[str, date, datetime]]) -> str:
    """Format a date or date-string for display in American English.

    Examples:
        format_date("2026-06-27")              -> "June 27, 2026"
        format_date(date(2026, 6, 27))         -> "June 27, 2026"
        format_date(datetime(2026, 6, 27))     -> "June 27, 2026"
        format_date(None)                      -> ""
        format_date("")                        -> ""
        format_date("not-a-date")              -> "not-a-date"  # fail-safe passthrough

    Accepts ISO 8601 date strings (YYYY-MM-DD) and full datetimes.
    Returns empty string on None/empty. Returns the original string
    unchanged if parsing fails, so the page never crashes on bad data.
    """
    if value is None or value == "":
        return ""

    # Already a date/datetime object: format directly
    if isinstance(value, datetime):
        return value.strftime("%B %d, %Y")
    if isinstance(value, date):
        return value.strftime("%B %d, %Y")

    # String input: parse ISO format, take first 10 chars (YYYY-MM-DD)
    if isinstance(value, str):
        try:
            iso_part = value[:10]
            parsed = date.fromisoformat(iso_part)
            return parsed.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            return value  # fail-safe: return original on parse error

    # Unknown type: cast to string and return
    return str(value)


def parse_date(value: Optional[Union[str, date, datetime]]) -> Optional[date]:
    """Inverse of format_date(): returns a date object from any input.

    Accepts:
      - None or ""           -> returns None
      - datetime.date object -> returned as-is
      - datetime.datetime    -> .date() extracted
      - ISO date string      -> parsed via date.fromisoformat()
      - ISO timestamp string -> first 10 chars parsed via date.fromisoformat()

    Returns a date object or None. Never raises on valid CC Platform data.
    Use this when reading event_date / payment_date / due_date from the DB
    and feeding it to st.date_input(value=...).
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except (ValueError, TypeError):
            return None
    return None


def format_date_short(value: Optional[Union[str, date, datetime]]) -> str:
    """Short date format for tight columns: 'Jun 27, 2026' instead of 'June 27, 2026'.

    Same input handling as format_date(). Useful when column width is limited.
    """
    if value is None or value == "":
        return ""

    if isinstance(value, datetime):
        return value.strftime("%b %d, %Y")
    if isinstance(value, date):
        return value.strftime("%b %d, %Y")

    if isinstance(value, str):
        try:
            iso_part = value[:10]
            parsed = date.fromisoformat(iso_part)
            return parsed.strftime("%b %d, %Y")
        except (ValueError, TypeError):
            return value

    return str(value)
