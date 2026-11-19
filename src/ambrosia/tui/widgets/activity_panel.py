"""Activity / timeline panel: recent actions, progress, artifacts, warnings."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from textual.containers import VerticalScroll
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.tui.services import TUIServiceAdapter

logger = logging.getLogger(__name__)


class ActivityPanel(VerticalScroll):
    """Right sidebar showing the execution timeline and recent activity."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(id=id)
        self._services = services
        self._entries: list[str] = []
        self._max_entries = 200

    def compose(self) -> ComposeResult:
        yield Static(id="activity-log")

    # ------------------------------------------------------------------ entries

    def add_entry(self, text: str) -> None:
        self._entries.append(text)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]
        try:
            log = self.query_one("#activity-log", Static)
            log.update("\n".join(self._entries))
            self.scroll_end(animate=False)
        except Exception as exc:  # pragma: no cover - log not yet mounted
            logger.debug("Activity log not ready for update: %s", exc)

    def clear(self) -> None:
        self._entries = []
        try:
            self.query_one("#activity-log", Static).update("")
        except Exception as exc:  # pragma: no cover - log not yet mounted
            logger.debug("Activity log not ready to clear: %s", exc)

    def refresh_context(self) -> None:
        self.refresh()


__all__ = ["ActivityPanel"]
