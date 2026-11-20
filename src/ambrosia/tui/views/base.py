"""Base class for TUI views."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.css.query import NoMatches
from textual.widget import Widget

if TYPE_CHECKING:
    from ambrosia.tui.app import AmbrosiaApp
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

    @property
    def workspace(self) -> AmbrosiaApp:
        """The owning application, typed so views can read/write shared context."""
        return cast("AmbrosiaApp", self.app)

    async def refresh_view(self) -> None:
        """Called by the app when context changes so the view redraws."""
        self.refresh()

    async def safe_refresh(self) -> None:
        """Refresh only while still mounted, tolerating stale callbacks.

        Navigation removes views asynchronously; a refresh scheduled just before
        a view is replaced may run afterwards. Ignore such callbacks instead of
        letting a missing-widget error crash the message loop.
        """
        if not self.is_mounted:
            return
        try:
            await self.refresh_view()
        except NoMatches:
            return


__all__ = ["BaseView"]
