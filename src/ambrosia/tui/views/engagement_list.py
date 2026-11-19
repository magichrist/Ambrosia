"""Engagement selection / creation view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from ambrosia.application.engagement_service import EngagementDTO
from ambrosia.tui.services import TUIServiceAdapter
from ambrosia.tui.views.base import BaseView


class EngagementListView(BaseView):
    """List engagements, open one, or create a new one."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(services, id=id)
        self._engagements: list[EngagementDTO] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Engagements", id="engagements-title")
            yield Static("Select an engagement to open it, or create a new one.", id="hint")
            yield ListView(id="engagements-list")
            yield Label("Create new engagement", id="create-title")
            yield Input(placeholder="Name", id="engagement-name")
            yield Input(placeholder="Description (optional)", id="engagement-description")
            with Vertical():
                yield Button("Create", id="create-engagement", variant="primary")
                yield Button("Refresh", id="refresh-engagements")

    def on_mount(self) -> None:
        self.refresh_engagements()

    def refresh_engagements(self) -> None:
        try:
            dto = self.services.list_engagements()
        except Exception:  # pragma: no cover - services unavailable
            dto = None
        self._engagements = dto.engagements if dto is not None else []
        list_view = self.query_one("#engagements-list", ListView)
        list_view.clear()
        for engagement in self._engagements:
            label = f"{engagement.name}  ({engagement.status})  {engagement.id[:8]}"
            list_view.append(ListItem(Static(label), id=engagement.id))

    def selected_engagement_id(self) -> str | None:
        item = self.query_one("#engagements-list", ListView).highlighted_child
        if item is None:
            return None
        return item.id

    def new_engagement_values(self) -> tuple[str, str | None]:
        name = self.query_one("#engagement-name", Input).value
        description = self.query_one("#engagement-description", Input).value or None
        return name, description


__all__ = ["EngagementListView"]
