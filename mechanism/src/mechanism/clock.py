"""Timekeeping.

Single canonical home for time math and formatting. Other modules import
from here and do not reach for `datetime`, `time`, or `pendulum` directly
— keeps the timekeeping register honest and audit-able.
"""

from __future__ import annotations

from datetime import datetime

import dateparser
import pendulum

from mechanism.settings import get_settings

LOCAL_TZ: str = get_settings().timezone
"""The configured local timezone (IANA name), from `timezone` in the env file."""

_DAY_START_HOUR = 6
"""The local hour that opens a new day. A 6 AM seam, not midnight."""


def now() -> pendulum.DateTime:
    """Return the current local time as a timezone-aware Pendulum DateTime."""
    return pendulum.now(LOCAL_TZ)


def start_of_day(dt: datetime | pendulum.DateTime) -> pendulum.DateTime:
    """Return the local-time start of the day that `dt` falls within.

    A "day" runs from one 6 AM local boundary to the next. A `dt` at 3 AM
    belongs to the previous day; a `dt` at 7 AM belongs to today.

    Args:
        dt: A timezone-aware datetime (stdlib or Pendulum).

    Returns:
        The local time that opens dt's day.
    """
    local = pendulum.instance(dt).in_timezone(LOCAL_TZ)
    opening = local.start_of("day").add(hours=_DAY_START_HOUR)
    if local < opening:
        opening = opening.subtract(days=1)
    return opening


def parse_when(value: str) -> datetime | None:
    """Parse a human or ISO 8601 date/time string into a timezone-aware datetime.

    Accepts ISO 8601 ("2025-05-07T12:00:00"), explicit dates ("May 7 2025"),
    and natural language ("yesterday", "two weeks ago"). Strings are resolved
    in `LOCAL_TZ`. Ambiguous relative phrases prefer past dates.

    Args:
        value: The user-supplied date string.

    Returns:
        A timezone-aware datetime, or None if the string can't be parsed.
    """
    return dateparser.parse(
        value,
        settings={
            "TIMEZONE": LOCAL_TZ,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "past",
        },
    )


def from_iso(value: str) -> pendulum.DateTime:
    """Parse a strict ISO 8601 timestamp string into a Pendulum DateTime.

    Stricter than `parse_when` — only accepts a full timestamp (date + time
    + offset), raising on anything else. Use this for round-tripping values
    we produced ourselves via `utc_iso` or `DateTime.isoformat()`.

    Args:
        value: An ISO 8601 timestamp string.

    Returns:
        The parsed timezone-aware Pendulum DateTime.

    Raises:
        ValueError: If `value` doesn't parse to a full timestamp.
    """
    parsed = pendulum.parse(value)
    if not isinstance(parsed, pendulum.DateTime):
        msg = f"expected ISO 8601 timestamp, got {type(parsed).__name__}: {value!r}"
        raise ValueError(msg)
    return parsed


def utc_iso(dt: datetime | pendulum.DateTime) -> str:
    """Format a datetime as an ISO 8601 string normalized to UTC.

    Counterpart to `pso8601` (which formats for human reading in
    `LOCAL_TZ`). Use this anywhere we're writing a timestamp for
    storage, wire transport, or any context where the consumer will
    render its own locale — same shape as how Postgres `timestamptz`
    columns travel and how wire events carry `createdAt` etc.

    Args:
        dt: A timezone-aware datetime.

    Returns:
        An ISO 8601 timestamp string in UTC (`"...+00:00"`).
    """
    return pendulum.instance(dt).in_timezone("UTC").isoformat()


def pso8601(dt: datetime | pendulum.DateTime) -> str:
    """Format a datetime in PSO-8601 (the household register).

    Examples:
        "Sun May 17 2026, 10:23 AM"
        "Fri Dec 31 2025, 9:05 PM"

    The result is rendered in `LOCAL_TZ`; the input may be in any timezone
    (it gets converted). 12-hour clock, no leading zero on hours, no
    timezone suffix.

    Args:
        dt: A timezone-aware datetime (stdlib or Pendulum).

    Returns:
        The formatted timestamp string.
    """
    local = pendulum.instance(dt).in_timezone(LOCAL_TZ)
    return local.format("ddd MMM D YYYY, h:mm A")


def elapsed(earlier: datetime | pendulum.DateTime, later: datetime | pendulum.DateTime) -> str:
    """Format the elapsed time between two datetimes in a human-friendly form.

    Buckets, by elapsed time:
        < 60s    -> "moments"
        < 60m    -> "N minutes"
        < 24h    -> "N hours"
        < 48h    -> "one day"
        < 7d     -> "N days"
        < 8w     -> "N weeks"
        else     -> "a long time"

    Singular forms drop the "s". For a "first message of the session"
    bucket use the literal returned for `< 60s` ("moments"); callers
    decide whether to invoke this at all for the no-previous case.

    Args:
        earlier: The earlier datetime.
        later: The later datetime.

    Returns:
        The elapsed string.
    """

    def _plural(n: int, unit: str) -> str:
        return f"{n} {unit}{'' if n == 1 else 's'}"

    diff = pendulum.instance(later) - pendulum.instance(earlier)
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "moments"
    minutes = seconds // 60
    if minutes < 60:
        return _plural(minutes, "minute")
    hours = minutes // 60
    if hours < 24:
        return _plural(hours, "hour")
    if hours < 48:
        return "one day"
    days = hours // 24
    if days < 7:
        return _plural(days, "day")
    weeks = days // 7
    if weeks < 8:
        return _plural(weeks, "week")
    return "a long time"


def age(dt: datetime | pendulum.DateTime) -> str:
    """Format the age of `dt` relative to now in a human-friendly form.

    Buckets, by elapsed time since `dt`:
        < 60s    -> "just now"
        < 60m    -> "N minutes ago"
        < 24h    -> "N hours ago"
        < 48h    -> "yesterday"
        < 7d     -> "N days ago"
        < 14d    -> "last week"
        < 8w     -> "N weeks ago"
        < 24mo   -> "N months ago"
        else     -> "N years ago"

    Singular forms drop the "s" ("1 hour ago", not "1 hours ago"). Future
    timestamps return "just now" — they shouldn't happen in practice and
    we don't want to invent a "in N minutes" branch that's never used.

    Args:
        dt: A timezone-aware datetime (stdlib or Pendulum).

    Returns:
        The age string.
    """

    def _plural(n: int, unit: str) -> str:
        return f"{n} {unit}{'' if n == 1 else 's'} ago"

    diff = now() - pendulum.instance(dt)
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return _plural(minutes, "minute")
    hours = minutes // 60
    if hours < 24:
        return _plural(hours, "hour")
    if hours < 48:
        return "yesterday"
    days = hours // 24
    if days < 7:
        return _plural(days, "day")
    if days < 14:
        return "last week"
    weeks = days // 7
    if weeks < 8:
        return _plural(weeks, "week")
    months = days // 30
    if months < 24:
        return _plural(months, "month")
    years = days // 365
    return _plural(years, "year")
