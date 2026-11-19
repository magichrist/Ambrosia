"""Dashboard view: context-recommended actions for the current engagement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Label, Static

from ambrosia.application.action_service import ActionCheckDTO, ActionDTO
from ambrosia.tui.views.base import BaseView
from ambrosia.tui.widgets.action_list import ActionList

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.tui.services import TUIServiceAdapter

_STATUS_ORDER = {
    "available": 0,
    "needs_input": 1,
    "needs_approval": 2,
    "blocked": 3,
    "missing_dependency": 4,
    "not_applicable": 5,
}


class DashboardView(BaseView):
    """Main workspace view: recommended actions shaped by the current context.

    Actions are ordered so the most usable ones surface first, but unavailable
    actions are never hidden — each shows its status and the reason why.
    """

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(services, id=id)
        self._action_list = ActionList(services, id="dashboard-actions")
        self._actions: list[tuple[ActionDTO, ActionCheckDTO]] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="dashboard-header")
            yield Label("Recommended actions", id="dashboard-subtitle")
            yield self._action_list
            yield Static(
                "Enter: open selected action   r: refresh suggestions   "
                "a: view all actions   j: job monitor   f: findings",
                id="dashboard-hint",
            )

    # ------------------------------------------------------------------ public

    def refresh_view(self) -> None:
        """Recompute availability for the current engagement + target context."""
        self.refresh_actions()

    def refresh_actions(self) -> None:
        """Recompute availability for the current engagement + target context."""
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        target_address = getattr(app, "current_target_address", None) or None

        header = self.query_one("#dashboard-header", Static)
        if engagement_id:
            try:
                engagement = self.services.get_engagement(engagement_id)
                header.update(
                    f"Engagement: {engagement.name}  ({engagement_id[:8]})  |  "
                    f"target: {target_address or '(none selected)'}"
                )
            except Exception:  # pragma: no cover - defensive display fallback
                header.update(
                    f"Engagement: {engagement_id}  |  target: {target_address or '(none)'}"
                )
        else:
            header.update("No engagement selected — open the engagement switcher (g)")

        actions: list[tuple[ActionDTO, ActionCheckDTO]] = []
        if engagement_id:
            try:
                listed = self.services.list_actions()
            except Exception:  # pragma: no cover - services unavailable
                listed = None
            if listed is not None:
                for dto in listed.actions:
                    try:
                        check = self.services.check_action(
                            dto.id,
                            engagement_id=engagement_id,
                            target_address=target_address,
                        )
                    except Exception:  # pragma: no cover - checker failure
                        check = ActionCheckDTO(
                            action_id=dto.id,
                            status="blocked",
                            reasons=["availability check failed"],
                            missing_inputs=[],
                            matched_artifact_ids=[],
                            required_approval=False,
                            allowed=False,
                        )
                    actions.append((dto, check))
        actions.sort(key=lambda pair: (_STATUS_ORDER.get(pair[1].status, 9), pair[0].id))
        self._actions = actions
        self._action_list.set_actions(actions)

    def selected_action(self) -> tuple[ActionDTO, ActionCheckDTO] | None:
        action_id = self._action_list.selected_action_id()
        if action_id is None:
            return None
        for dto, check in self._actions:
            if dto.id == action_id:
                return dto, check
        return None


__all__ = ["DashboardView"]
