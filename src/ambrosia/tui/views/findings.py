"""Findings / evidence view: validated issues and evidence artifacts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView, Static

from ambrosia.tui.views.base import BaseView

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.domain.models import Artifact
    from ambrosia.tui.services import TUIServiceAdapter


class FindingsView(BaseView):
    """List findings (evidence) for the current engagement and show details."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(services, id=id)
        self._findings: list[Artifact] = []

    def compose(self) -> ComposeResult:
        yield Label("Findings / evidence", id="findings-title")
        yield ListView(id="findings-list")
        yield Static(id="findings-body")
        with Vertical():
            yield Button("Refresh", id="refresh-findings")
            yield Button("Back", id="back-findings")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        body = self.query_one("#findings-body", Static)
        findings_list = self.query_one("#findings-list", ListView)
        findings_list.clear()
        self._findings = []
        if not engagement_id:
            body.update("No engagement selected.")
            return
        try:
            self._findings = list(self.services.list_findings(engagement_id))
        except Exception as exc:  # pragma: no cover - services unavailable
            body.update(f"Unable to load findings: {exc}")
            return
        for finding in self._findings:
            label = (
                f"{finding.id[:8]}  {finding.type}  "
                f"source={finding.source_kind or '-'}  target={finding.target_ref or '-'}"
            )
            findings_list.append(ListItem(Static(label), id=finding.id))
        if not self._findings:
            body.update("No findings recorded yet.")
        else:
            body.update(f"{len(self._findings)} finding(s). Select one to inspect.")

    def selected_finding_id(self) -> str | None:
        item = self.query_one("#findings-list", ListView).highlighted_child
        if item is None:
            return None
        return item.id


__all__ = ["FindingsView"]
