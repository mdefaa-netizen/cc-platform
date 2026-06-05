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


def format_timestamp_short(value: Optional[Union[str, date, datetime]]) -> str:
    """Format a timestamp for display as 'YYYY-MM-DD HH:MM'.

    Backend-agnostic: psycopg2 (Postgres / Supabase) returns timestamps as
    ``datetime`` objects, while sqlite3 returns them as strings. This helper
    accepts either, so callers can safely render ``created_at`` / ``replied_at``
    / ``logged_at`` / ``sent_date`` / ``generated_date`` columns without
    crashing when the deployment backend changes.

    Examples:
        format_timestamp_short(datetime(2026, 6, 5, 14, 30))   -> "2026-06-05 14:30"
        format_timestamp_short("2026-06-05 14:30:22.123456")   -> "2026-06-05 14:30"
        format_timestamp_short(date(2026, 6, 5))               -> "2026-06-05"
        format_timestamp_short(None)                           -> ""
        format_timestamp_short("")                             -> ""

    Returns "" for None/empty. Never raises on common DB return types.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        # Historical SQLite format: "YYYY-MM-DD HH:MM:SS[.ffff]".
        # Truncating to 16 chars yields "YYYY-MM-DD HH:MM".
        return value[:16]
    # Unknown type: stringify defensively and truncate.
    return str(value)[:16]


def format_date_short(value: Optional[Union[str, date, datetime]]) -> str:
    """Format a date or timestamp for display as 'YYYY-MM-DD'.

    Companion to ``format_timestamp_short`` for the date-only case. Backend-
    agnostic: psycopg2 (Postgres / Supabase) returns timestamps as ``datetime``
    objects, while sqlite3 returns them as strings. This helper accepts either,
    so callers can safely render ``created_at`` / ``sent_date`` / ``submitted_date``
    / ``calculated_at`` columns as a short date without crashing when the
    deployment backend changes — a bare ``value[:10]`` raises ``TypeError`` on
    a ``datetime`` object.

    Examples:
        format_date_short(datetime(2026, 6, 5, 14, 30))   -> "2026-06-05"
        format_date_short(date(2026, 6, 5))               -> "2026-06-05"
        format_date_short("2026-06-05 14:30:22.123456")   -> "2026-06-05"
        format_date_short("2026-06-05")                   -> "2026-06-05"
        format_date_short(None)                           -> ""
        format_date_short("")                             -> ""

    Returns "" for None/empty. Never raises on common DB return types.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, str):
        # Historical SQLite format: "YYYY-MM-DD[ HH:MM:SS[.ffff]]".
        # Truncating to 10 chars yields "YYYY-MM-DD".
        return value[:10]
    # Unknown type: stringify defensively and truncate.
    return str(value)[:10]
