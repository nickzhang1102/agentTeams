"""Datetime helpers that preserve the project's naive-UTC storage convention."""

from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """Return naive UTC without using deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
