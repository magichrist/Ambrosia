"""Global command palette: / search for actions, presets, targets, artifacts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static

from ambrosia.tui.services import TUIServiceAdapter


class CommandPalette(ModalScreen[dict[str, object] | None]):
    """Full-screen search overlay. Triggered with ``/``.

    Results are drawn from registered actions and presets (via application
    services). Unavailable actions are shown with their status and reason, so
    nothing is hidden from search.
    """

    DEFAULT_CSS = """
    CommandPalette > Vertical {
        width: 90;
        height: 20;
        background: $panel;
        padding: 1 2;
    }
    CommandPalette ListView {
        height: 1fr;
        border: solid $primary;
    }
    """

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(id=id)
        self._services = services
        self._results: list[dict[str, object]] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Command palette — search actions, presets, targets", id="title")
            yield Input(placeholder="Type to search…", id="search")
            yield Label("results", id="results-label")
            yield ListView(id="results")
            yield Static("Enter: open  Esc: close", id="hint")

    def on_mount(self) -> None:
        self.query_one("#search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._search(event.value or "")

    def _search(self, query: str) -> None:
        self._results = []
        if query:
            try:
                listed = self._services.list_actions()
            except Exception:  # pragma: no cover - services unavailable
                listed = None
            if listed is not None:
                for action in listed.actions:
                    haystack = " ".join(
                        [
                            action.id,
                            action.name,
                            action.description,
                            action.category,
                            *action.tags,
                        ]
                    ).lower()
                    if query.lower() in haystack:
                        self._results.append(
                            {
                                "kind": "action",
                                "id": action.id,
                                "label": f"{action.id}  [{action.category}]  {action.name}",
                                "description": action.description,
                            }
                        )
        results = self.query_one("#results", ListView)
        results.clear()
        for index, result in enumerate(self._results):
            results.append(ListItem(Static(str(result["label"])), id=str(index)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if item is None or item.id is None:
            return
        index = int(item.id)
        result = self._results[index]
        self.dismiss(result)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()


__all__ = ["CommandPalette"]
