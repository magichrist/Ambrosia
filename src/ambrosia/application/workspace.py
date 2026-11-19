"""Workspace-local state for the CLI.

The CLI is stateless between invocations except for a small workspace state
file (``.ambrosia/state.json`` in the current working directory) that records
the current engagement. Commands can override it with ``--engagement``.
"""

from __future__ import annotations

import json
from pathlib import Path

STATE_FILE_NAME = "state.json"
WORKSPACE_DIR_NAME = ".ambrosia"


def workspace_dir() -> Path:
    """Return the Ambrosia workspace directory for the current working directory."""
    return Path.cwd() / WORKSPACE_DIR_NAME


def state_path() -> Path:
    """Return the path of the workspace state file."""
    return workspace_dir() / STATE_FILE_NAME


def read_current_engagement() -> str | None:
    """Return the current engagement id from workspace state, or ``None``."""
    path = state_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    engagement_id = data.get("current_engagement")
    return engagement_id if isinstance(engagement_id, str) else None


def write_current_engagement(engagement_id: str) -> None:
    """Record ``engagement_id`` as the current engagement in workspace state."""
    directory = workspace_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = state_path()
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    data["current_engagement"] = engagement_id
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


__all__ = ["read_current_engagement", "write_current_engagement", "workspace_dir", "state_path"]
