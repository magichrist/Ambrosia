"""Base class for TUI views."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widget import Widget

if TYPE_CHECKING:
    from ambrosia.tui.services import TUIServiceAdapter


class BaseView(Widget):
    """A view rendered inside the persistent workspace shell.

    Views preserve navigation state through the owning application: the current
    engagement and target live on the app, not inside the view, so moving
    between views never loses context.
    """

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(id=id)
        self.services = services

    def refresh_view(self) -> None:
        """Called by the app when context changes so the view redraws."""
        self.refresh()


__all__ = ["BaseView"]
