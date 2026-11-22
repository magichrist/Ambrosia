"""Helpers for turning data values into valid Textual widget ids.

Preset ids like ``http.observation_18`` and tags like ``web scanning`` contain
characters Textual rejects in widget identifiers, so every generated id is
passed through :func:`safe_widget_id`.
"""

from __future__ import annotations

import re

_INVALID = re.compile(r"[^A-Za-z0-9_-]")


def safe_widget_id(value: str) -> str:
    """Return ``value`` with only characters allowed in a Textual id."""
    cleaned = _INVALID.sub("_", value).strip("_")
    if not cleaned or cleaned[0].isdigit() or cleaned[0] == "-":
        cleaned = "id_" + cleaned
    return cleaned


__all__ = ["safe_widget_id"]
