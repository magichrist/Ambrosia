"""Append-only execution history log for Ambrosia v2.

:class:`HistoryStore` records each executed command as a single JSON line in a
JSONL file (``~/.ambrosia/history.jsonl`` by default). History recording is
opt-in: :attr:`HistoryStore.enabled` defaults to ``False`` and a disabled store
is a no-op, so no history file is created unless an operator opts in.

This module is purely a data layer: it is not integrated with the TUI, CLI,
or executor. Integration happens separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

__all__ = ["HistoryEntry", "HistoryStore", "make_entry"]

DEFAULT_HISTORY_PATH = Path.home() / ".ambrosia" / "history.jsonl"


@dataclass(frozen=True)
class HistoryEntry:
    """A single executed command record.

    ``argv`` is the resolved argument list that ran. ``exit_code`` is ``None``
    when the command did not produce an exit code (e.g. it was cancelled).
    """

    command_id: str
    command_name: str
    argv: list[str]
    exit_code: int | None
    duration_ms: int
    ran_at: str
    cancelled: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize this entry to a JSON-friendly dict."""
        return {
            "command_id": self.command_id,
            "command_name": self.command_name,
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "ran_at": self.ran_at,
            "cancelled": self.cancelled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        """Deserialize an entry from a JSON dict, tolerating missing keys."""
        argv_raw = data.get("argv", [])
        if not isinstance(argv_raw, list):
            argv_raw = []
        argv = [str(item) for item in argv_raw]

        exit_code_raw = data.get("exit_code")
        exit_code: int | None = None
        if isinstance(exit_code_raw, int) and not isinstance(exit_code_raw, bool):
            exit_code = exit_code_raw

        duration_raw = data.get("duration_ms", 0)
        duration_ms = 0
        if isinstance(duration_raw, int) and not isinstance(duration_raw, bool):
            duration_ms = duration_raw

        return cls(
            command_id=str(data.get("command_id", "")),
            command_name=str(data.get("command_name", "")),
            argv=argv,
            exit_code=exit_code,
            duration_ms=duration_ms,
            ran_at=str(data.get("ran_at", "")),
            cancelled=bool(data.get("cancelled", False)),
        )


class HistoryStore:
    """Append-only JSONL store of :class:`HistoryEntry` records.

    Writing is opt-in: a disabled store never touches the filesystem. Entries
    are appended one JSON line at a time (file opened in append mode and
    flushed after each write). Reads degrade gracefully: missing or unreadable
    files and individually malformed lines are skipped.
    """

    def __init__(self, path: str | Path = DEFAULT_HISTORY_PATH) -> None:
        self._path = Path(path)
        self.enabled = False

    # ------------------------------------------------------------------ public API

    def add(self, entry: HistoryEntry) -> None:
        """Append ``entry`` as one JSON line to the history file.

        No-op when the store is disabled. Creates parent directories as needed.
        """
        if not self.enabled:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()

    def read(self, limit: int = 100) -> list[HistoryEntry]:
        """Return the last ``limit`` entries from the history file.

        Returns an empty list when the file is missing or unreadable.
        Individually malformed lines are skipped.
        """
        if not self._path.exists():
            return []
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries: list[HistoryEntry] = []
        for line in raw.splitlines():
            entry = self._parse_line(line)
            if entry is not None:
                entries.append(entry)
        start = max(0, len(entries) - limit)
        return entries[start:]

    def clear(self) -> None:
        """Truncate the history file. Not an error if the file is missing."""
        if self._path.exists():
            self._path.write_text("", encoding="utf-8")

    # ------------------------------------------------------------------ internals

    def _parse_line(self, line: str) -> HistoryEntry | None:
        """Parse one JSONL line into an entry, or ``None`` if it is unusable."""
        if not line.strip():
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        try:
            return HistoryEntry.from_dict(data)
        except (TypeError, ValueError):
            return None


def make_entry(
    command_id: str,
    command_name: str,
    argv: list[str],
    exit_code: int | None,
    duration_ms: int,
    cancelled: bool = False,
) -> HistoryEntry:
    """Create a :class:`HistoryEntry` with ``ran_at`` set to now (ISO 8601)."""
    return HistoryEntry(
        command_id=command_id,
        command_name=command_name,
        argv=list(argv),
        exit_code=exit_code,
        duration_ms=duration_ms,
        ran_at=datetime.now(UTC).isoformat(),
        cancelled=cancelled,
    )
