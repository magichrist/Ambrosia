"""Session state for the v2 command launcher.

Session state is a nested mapping ``command_id -> {input_id: value}`` of the
values an operator has provided for each command's inputs. :class:`SessionState`
holds the mapping in memory; :class:`SessionStore` persists it to (and loads it
from) a JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


class SessionState:
    """Mutable session state held in memory for the lifetime of a TUI process."""

    def __init__(self, values: dict[str, dict[str, str]] | None = None) -> None:
        self._values: dict[str, dict[str, str]] = {
            command_id: dict(inputs) for command_id, inputs in (values or {}).items()
        }

    # ------------------------------------------------------------------ public API

    def get(self, command_id: str, input_id: str) -> str | None:
        """Return the remembered value for ``(command_id, input_id)`` or ``None``."""
        return self._values.get(command_id, {}).get(input_id)

    def get_all(self, command_id: str) -> dict[str, str]:
        """Return a copy of all remembered values for ``command_id``."""
        return dict(self._values.get(command_id, {}))

    def set(self, command_id: str, input_id: str, value: str) -> None:
        """Remember ``value`` for ``(command_id, input_id)``."""
        self._values.setdefault(command_id, {})[input_id] = value

    def set_all(self, command_id: str, values: dict[str, str]) -> None:
        """Remember all of ``values`` for ``command_id`` (replacing prior values)."""
        self._values[command_id] = dict(values)

    def has_all_required(self, command_id: str, required_ids: Iterable[str]) -> bool:
        """Return True if every id in ``required_ids`` has a non-empty value."""
        values = self._values.get(command_id, {})
        return all(bool(values.get(input_id, "")) for input_id in required_ids)

    def to_dict(self) -> dict[str, dict[str, str]]:
        """Return a JSON-friendly copy of the whole state."""
        return {command_id: dict(inputs) for command_id, inputs in self._values.items()}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SessionState:
        """Rebuild state from a JSON-loaded dict, tolerating missing keys."""
        values: dict[str, dict[str, str]] = {}
        if isinstance(data, dict):
            for command_id, inputs in data.items():
                if isinstance(inputs, dict):
                    values[str(command_id)] = {str(k): str(v) for k, v in inputs.items()}
        return cls(values)


class SessionStore:
    """Persist :class:`SessionState` to and load it from a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    # ------------------------------------------------------------------ public API

    def load(self) -> SessionState:
        """Load session state from the JSON file.

        Returns an empty :class:`SessionState` when the file does not exist or
        contains invalid JSON (graceful degradation, never crashes on a corrupt
        session file).
        """
        if not self._path.exists():
            return SessionState()
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return SessionState()
        return SessionState.from_dict(data)

    def save(self, session: SessionState) -> None:
        """Persist ``session`` to the JSON file, creating parent directories."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as fh:
            json.dump(session.to_dict(), fh, indent=2)
