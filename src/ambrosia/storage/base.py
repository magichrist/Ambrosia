"""SQLAlchemy declarative base and shared storage primitives.

ORM models live privately in this package. ORM instances must never escape
into domain, UI, or application packages; repository boundaries convert ORM
rows into domain models (see ``converters.py``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


def utc_now() -> datetime:
    """Current time as an aware UTC datetime.

    Storage always persists aware UTC datetimes. Domain models carry naive
    datetimes that are interpreted as UTC; converters translate between the
    two representations at the storage boundary.
    """
    return datetime.now(timezone.utc)


def to_storage_dt(value: datetime) -> datetime:
    """Convert a domain (naive UTC) datetime to aware UTC for persistence."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def from_storage_dt(value: datetime | None) -> datetime | None:
    """Convert an aware stored datetime back to a naive UTC domain datetime."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class JSONType(TypeDecorator[Any]):
    """A validated JSON column.

    Values are serialized with :func:`json.dumps` using ``allow_nan=False`` so
    only valid JSON is persisted. On read, the parsed value is returned; the
    consuming domain model performs structural validation at the repository
    boundary.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, allow_nan=False, sort_keys=True)

    def process_result_value(self, value: str | None, dialect: Any) -> Any:
        if value is None:
            return None
        return json.loads(value)


class Base(DeclarativeBase):
    """Declarative base for all Ambrosia ORM models."""

    type_annotation_map = {
        dict[str, object]: JSONType(),
    }


__all__ = ["Base", "JSONType", "utc_now", "to_storage_dt", "from_storage_dt"]
