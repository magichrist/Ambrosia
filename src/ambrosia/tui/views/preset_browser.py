"""Preset browser view: list, validate, and plan presets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView, Static

from ambrosia.tui.views.base import BaseView

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.application.preset_service import PresetDTO
    from ambrosia.tui.services import TUIServiceAdapter


class PresetBrowserView(BaseView):
    """Browse available presets and inspect their dry-run plans."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(services, id=id)
        self._presets: list[PresetDTO] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Presets", id="presets-title")
            yield ListView(id="presets-list")
            yield Static(id="presets-body")
            with Vertical():
                yield Button("Refresh", id="refresh-presets")
                yield Button("Validate selected", id="validate-preset")
                yield Button("Plan selected (dry run)", id="plan-preset")
                yield Button("Back", id="back-presets")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        body = self.query_one("#presets-body", Static)
        preset_list = self.query_one("#presets-list", ListView)
        preset_list.clear()
        self._presets = []
        try:
            dto = self.services.list_presets()
        except Exception as exc:  # pragma: no cover - services unavailable
            body.update(f"Unable to load presets: {exc}")
            return
        self._presets = list(dto.presets)
        for preset in self._presets:
            path = getattr(preset, "path", "") or ""
            label = (
                f"{preset.id}  v{preset.version}  {preset.step_count} steps  "
                f"{path.split('/')[-1] if path else preset.id}"
            )
            preset_list.append(ListItem(Static(label), id=preset.id))
        if not self._presets:
            body.update("No presets found.")
        else:
            body.update(f"{len(self._presets)} preset(s). Select one and choose validate or plan.")

    def selected_preset_id(self) -> str | None:
        item = self.query_one("#presets-list", ListView).highlighted_child
        if item is None:
            return None
        return item.id


__all__ = ["PresetBrowserView"]
