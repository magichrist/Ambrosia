"""Action list widget: renders actions with availability state and reasons."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import ListItem, ListView, Static

if TYPE_CHECKING:
    from ambrosia.application.action_service import ActionCheckDTO, ActionDTO
    from ambrosia.tui.services import TUIServiceAdapter

_STATUS_STYLE = {
    "available": "#00ff88",
    "needs_input": "#ffd066",
    "needs_approval": "#ffd066",
    "blocked": "#ff6666",
    "missing_dependency": "#ff6666",
    "not_applicable": "#cccccc",
}


class ActionList(ListView):
    """A list of actions, each annotated with its availability status.

    Unavailable actions are never hidden: they are shown with their status and
    the reason why they cannot (yet) run.
    """

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(id=id)
        self._services = services
        self._actions: list[tuple[ActionDTO, ActionCheckDTO]] = []

    async def set_actions(self, actions: list[tuple[ActionDTO, ActionCheckDTO]]) -> None:
        self._actions = list(actions)
        await self.clear()
        for dto, check in self._actions:
            await self.append(self._make_item(dto, check))

    def _make_item(self, dto: ActionDTO, check: ActionCheckDTO) -> ListItem:
        text = Text()
        text.append(f"{dto.id}  ", style="bold")
        text.append(f"[{check.status}] ", style=_STATUS_STYLE.get(check.status, ""))
        text.append(dto.name, style="bold")
        if dto.description:
            text.append(f" — {dto.description}")
        if check.reasons:
            text.append("  |  ", style="dim")
            text.append("; ".join(check.reasons), style="#cccccc")
        if check.missing_inputs:
            text.append("  [missing: ", style="dim #ffd066")
            text.append(", ".join(check.missing_inputs), style="#ffd066")
            text.append("]", style="dim #ffd066")
        if check.required_approval:
            text.append("  [approval required]", style="#ffd066")
        return ListItem(Static(text), id=dto.id)

    def selected_action_id(self) -> str | None:
        item = self.highlighted_child
        if item is None:
            return None
        return item.id


__all__ = ["ActionList"]
