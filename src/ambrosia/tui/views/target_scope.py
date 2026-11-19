"""Target / scope view: the authorized engagement boundary."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from ambrosia.application.scope_service import ScopeDTO
from ambrosia.application.target_service import TargetListDTO
from ambrosia.tui.services import TUIServiceAdapter
from ambrosia.tui.views.base import BaseView


class TargetScopeView(BaseView):
    """Show and edit the engagement scope and its targets."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(services, id=id)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="scope-header")
            yield Static(id="scope-body")
            yield Label("Targets", id="targets-title")
            yield ListView(id="targets-list")
            yield Label("Add target", id="add-title")
            yield Input(placeholder="host / IP / domain", id="target-address")
            yield Button("Add target", id="add-target", variant="primary")
            yield Button("Refresh", id="refresh-scope")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        header = self.query_one("#scope-header", Static)
        if not engagement_id:
            header.update("No engagement selected")
            self.query_one("#scope-body", Static).update("Open an engagement to view its scope.")
            self.query_one("#targets-list", ListView).clear()
            return
        scope: ScopeDTO | None = None
        try:
            scope = self.services.show_scope(engagement_id)
        except Exception:  # pragma: no cover - services unavailable
            scope = None
        if scope is None:
            header.update(f"Scope for engagement {engagement_id[:8]}: (none defined)")
            self.query_one("#scope-body", Static).update(
                "No scope defined — nothing is authorized."
            )
        else:
            header.update(f"Scope for engagement {engagement_id[:8]}")
            lines = [
                f"include_hosts:      {', '.join(scope.include_hosts) or '(none)'}",
                f"include_cidrs:      {', '.join(scope.include_cidrs) or '(none)'}",
                f"include_domains:    {', '.join(scope.include_domains) or '(none)'}",
                f"exclude_hosts:      {', '.join(scope.exclude_hosts) or '(none)'}",
                f"exclude_cidrs:      {', '.join(scope.exclude_cidrs) or '(none)'}",
                f"allowed_ports:      {', '.join(str(p) for p in (scope.allowed_ports or [])) or '(none)'}",
                f"allowed_effects:    {', '.join(scope.allowed_effects)}",
                f"require_approval:   {', '.join(scope.require_approval_for)}",
                f"max_concurrency:    {scope.max_concurrency}",
            ]
            self.query_one("#scope-body", Static).update("\n".join(lines))
        targets: TargetListDTO | None = None
        try:
            targets = self.services.list_targets(engagement_id)
        except Exception:  # pragma: no cover - services unavailable
            targets = None
        target_list = self.query_one("#targets-list", ListView)
        target_list.clear()
        if targets is not None:
            for target in targets.targets:
                target_list.append(
                    ListItem(
                        Static(f"{target.address}  ({target.kind})  {target.id[:8]}"),
                        id=target.id,
                    )
                )


__all__ = ["TargetScopeView"]
