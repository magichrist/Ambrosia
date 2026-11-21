"""Session state for the v2 command launcher.

Session state is a nested mapping ``command_id -> {input_id: value}`` of the
values an operator has provided for each command's inputs. :class:`SessionState`
holds the mapping in memory, tracks which inputs are secret, and keeps a short
history of recent command runs; :class:`SessionStore` persists it to (and loads
it from) a JSON file atomically. Secret input values are excluded from persisted
output by default.

:class:`SessionStore` also supports named session files stored in a
``sessions/`` subdirectory (``~/.ambrosia/sessions/<name>.json`` by default),
via :meth:`SessionStore.for_name`, :meth:`SessionStore.list_sessions`, and
:meth:`SessionStore.delete_session`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


class SessionState:
    """Mutable session state held in memory for the lifetime of a TUI process."""

    def __init__(
        self,
        values: dict[str, dict[str, str]] | None = None,
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._values: dict[str, dict[str, str]] = {
            command_id: dict(inputs) for command_id, inputs in (values or {}).items()
        }
        self._dirty = False
        self._secret_inputs: dict[str, set[str]] = {}
        self._recent: list[dict[str, str]] = []
        self._on_change = on_change

    # ------------------------------------------------------------------ public API

    @property
    def is_dirty(self) -> bool:
        """True if the in-memory state has unsaved changes."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Mark the state as having unsaved changes and notify listeners."""
        self._dirty = True
        self._notify_change()

    def mark_clean(self) -> None:
        """Mark the state as saved (no unsaved changes)."""
        self._dirty = False

    def on_change(self, callback: Callable[[], None]) -> None:
        """Register ``callback`` to invoke whenever the state is mutated."""
        self._on_change = callback

    def register_secret_inputs(self, command_id: str, input_ids: Iterable[str]) -> None:
        """Record ``input_ids`` as secret for ``command_id``.

        Secret inputs are excluded from :meth:`to_dict` (and therefore from the
        persisted session file) when ``exclude_secrets`` is true.
        """
        self._secret_inputs.setdefault(command_id, set()).update(input_ids)

    def clear(self) -> None:
        """Reset all remembered values and secret registrations.

        Clearing is a mutation, so the state is marked dirty afterwards.
        """
        self._values.clear()
        self._secret_inputs.clear()
        self._notify_change()

    def get(self, command_id: str, input_id: str) -> str | None:
        """Return the remembered value for ``(command_id, input_id)`` or ``None``."""
        return self._values.get(command_id, {}).get(input_id)

    def get_all(self, command_id: str) -> dict[str, str]:
        """Return a copy of all remembered values for ``command_id``."""
        return dict(self._values.get(command_id, {}))

    def set(self, command_id: str, input_id: str, value: str) -> None:
        """Remember ``value`` for ``(command_id, input_id)``."""
        self._values.setdefault(command_id, {})[input_id] = value
        self._notify_change()

    def set_all(self, command_id: str, values: dict[str, str]) -> None:
        """Remember all of ``values`` for ``command_id`` (replacing prior values)."""
        self._values[command_id] = dict(values)
        self._notify_change()

    def has_all_required(self, command_id: str, required_ids: Iterable[str]) -> bool:
        """Return True if every id in ``required_ids`` has a non-empty value."""
        values = self._values.get(command_id, {})
        return all(bool(values.get(input_id, "")) for input_id in required_ids)

    def add_recent(self, command_id: str, name: str) -> None:
        """Record a recent command run.

        The entry ``{command_id, name, ran_at}`` is added most-recent-first.
        Existing entries for the same ``command_id`` are removed first (dedupe
        by command_id, moving the entry to the front), and the list is capped
        at 50 entries. Recent tracking is separate from input memory.
        """
        entry = {
            "command_id": command_id,
            "name": name,
            "ran_at": datetime.now(UTC).isoformat(),
        }
        self._recent = [
            existing for existing in self._recent if existing["command_id"] != command_id
        ]
        self._recent.insert(0, entry)
        del self._recent[50:]
        self._notify_change()

    def get_recent(self, limit: int = 10) -> list[dict[str, str]]:
        """Return up to ``limit`` most recent command-run entries.

        Copies are returned so callers cannot mutate the internal history.
        """
        return [dict(entry) for entry in self._recent[:limit]]

    def to_dict(self, exclude_secrets: bool = False) -> dict[str, object]:
        """Return a JSON-friendly copy of the whole state.

        When ``exclude_secrets`` is true, input values registered as secret via
        :meth:`register_secret_inputs` are omitted, so secrets are not written
        to disk by default.
        """
        if not exclude_secrets:
            result: dict[str, object] = {
                command_id: dict(inputs) for command_id, inputs in self._values.items()
            }
        else:
            result = {}
            for command_id, inputs in self._values.items():
                secrets = self._secret_inputs.get(command_id)
                if secrets:
                    result[command_id] = {
                        input_id: value
                        for input_id, value in inputs.items()
                        if input_id not in secrets
                    }
                else:
                    result[command_id] = dict(inputs)
        if self._recent:
            result["_recent"] = [dict(entry) for entry in self._recent]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SessionState:
        """Rebuild state from a JSON-loaded dict, tolerating missing keys.

        A freshly loaded state is not dirty: it matches what is on disk.
        Recent command runs stored under the ``_recent`` key are restored;
        a missing or malformed key degrades gracefully to an empty history.
        """
        values: dict[str, dict[str, str]] = {}
        recent: list[dict[str, str]] = []
        if isinstance(data, dict):
            for command_id, inputs in data.items():
                if command_id == "_recent":
                    continue
                if isinstance(inputs, dict):
                    values[str(command_id)] = {str(k): str(v) for k, v in inputs.items()}
            raw_recent = data.get("_recent")
            if isinstance(raw_recent, list):
                for entry in raw_recent:
                    if (
                        isinstance(entry, dict)
                        and isinstance(entry.get("command_id"), str)
                        and isinstance(entry.get("name"), str)
                    ):
                        recent.append(
                            {
                                "command_id": entry["command_id"],
                                "name": entry["name"],
                                "ran_at": str(entry.get("ran_at", "")),
                            }
                        )
        state = cls(values)
        state._recent = recent
        return state

    # ------------------------------------------------------------------ internals

    def _notify_change(self) -> None:
        """Mark dirty and invoke the change listener, if any."""
        self._dirty = True
        if self._on_change is not None:
            self._on_change()


class SessionStore:
    """Persist :class:`SessionState` to and load it from a JSON file."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    # ------------------------------------------------------------------ named sessions

    @classmethod
    def for_name(cls, name: str, base_dir: Path | None = None) -> SessionStore:
        """Return a :class:`SessionStore` for the named session file.

        The file is ``<base_dir>/sessions/<name>.json``; when ``base_dir`` is
        omitted it defaults to ``~/.ambrosia``, i.e.
        ``~/.ambrosia/sessions/<name>.json``.
        """
        directory = (base_dir or Path.home() / ".ambrosia") / "sessions"
        return cls(directory / f"{name}.json")

    @classmethod
    def list_sessions(cls, base_dir: Path | None = None) -> list[str]:
        """List available session names (filenames without ``.json``).

        Looks in ``<base_dir>/sessions``; defaults to ``~/.ambrosia/sessions``.
        Returns an empty list when the directory does not exist.
        """
        directory = (base_dir or Path.home() / ".ambrosia") / "sessions"
        if not directory.is_dir():
            return []
        return sorted(
            path.stem for path in directory.iterdir() if path.is_file() and path.suffix == ".json"
        )

    @classmethod
    def delete_session(cls, name: str, base_dir: Path | None = None) -> None:
        """Remove the named session file, if it exists.

        Looks in ``<base_dir>/sessions``; defaults to ``~/.ambrosia/sessions``.
        It is not an error if the file (or directory) is missing.
        """
        directory = (base_dir or Path.home() / ".ambrosia") / "sessions"
        if directory.is_dir():
            (directory / f"{name}.json").unlink(missing_ok=True)

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

    def save(self, session: SessionState, exclude_secrets: bool = True) -> None:
        """Persist ``session`` to the JSON file atomically.

        The payload is written to a temporary file in the same directory and
        then renamed over the target with :meth:`Path.replace`, so a crash
        mid-write never leaves a partially-written session file. Parent
        directories are created as needed.

        When ``exclude_secrets`` is true (the default), secret input values
        registered on the session are omitted from the file.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(session.to_dict(exclude_secrets=exclude_secrets), indent=2) + "\n"
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(self._path.parent),
            prefix=self._path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)
        try:
            temp_path.replace(self._path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise
