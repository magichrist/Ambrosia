"""Artifact browser view: inspect typed artifacts produced during an engagement."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView, Static

from ambrosia.domain.models import Artifact
from ambrosia.tui.services import TUIServiceAdapter
from ambrosia.tui.views.base import BaseView


class ArtifactBrowserView(BaseView):
    """List engagement artifacts and show the details of a selected one."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(services, id=id)
        self._artifacts: list[Artifact] = []

    def compose(self) -> ComposeResult:
        yield Label("Artifacts", id="artifacts-title")
        yield ListView(id="artifacts-list")
        yield Static(id="artifacts-body")
        with Vertical():
            yield Button("Refresh", id="refresh-artifacts")
            yield Button("Back", id="back-artifacts")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        body = self.query_one("#artifacts-body", Static)
        artifact_list = self.query_one("#artifacts-list", ListView)
        artifact_list.clear()
        self._artifacts = []
        if not engagement_id:
            body.update("No engagement selected.")
            return
        try:
            self._artifacts = list(self.services.list_artifacts(engagement_id))
        except Exception as exc:  # pragma: no cover - services unavailable
            body.update(f"Unable to load artifacts: {exc}")
            return
        for artifact in self._artifacts:
            label = f"{artifact.id[:8]}  {artifact.type}  target={artifact.target_ref or '-'}"
            artifact_list.append(ListItem(Static(label), id=artifact.id))
        if not self._artifacts:
            body.update("No artifacts yet. Run actions to produce typed evidence.")
        else:
            body.update(
                f"{len(self._artifacts)} artifact(s). Select one and press Enter to inspect."
            )

    def selected_artifact_id(self) -> str | None:
        item = self.query_one("#artifacts-list", ListView).highlighted_child
        if item is None:
            return None
        return item.id

    def selected_artifact(self) -> Artifact | None:
        artifact_id = self.selected_artifact_id()
        if artifact_id is None:
            return None
        for artifact in self._artifacts:
            if artifact.id == artifact_id:
                return artifact
        return None


__all__ = ["ArtifactBrowserView"]
