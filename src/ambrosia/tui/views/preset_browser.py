"""Preset browser view: list, validate, and plan presets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView, Static

from ambrosia.tui.views.base import BaseView
from ambrosia.tui.widgets.modals import InputFormModal

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.application.preset_service import PresetDTO, PresetSaveDTO
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
                yield Button("Save a copy...", id="save-preset")
                yield Button("Back", id="back-presets")

    def on_mount(self) -> None:
        # Defer until composed children are available in the DOM.
        self.call_after_refresh(self.safe_refresh)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "refresh-presets":
            self.call_after_refresh(self.safe_refresh)
            return
        if button_id == "back-presets":
            self.workspace.action_go_back()
            return
        if button_id == "save-preset":
            self._open_save_dialog()
            return
        preset_id = self.selected_preset_id()
        if preset_id is None:
            self.query_one("#presets-body", Static).update("Select a preset first.")
            return
        selected = next((p for p in self._presets if p.id == preset_id), None)
        if selected is None:  # pragma: no cover - defensive
            return
        body = self.query_one("#presets-body", Static)
        try:
            if button_id == "validate-preset":
                result = self.services.validate_preset(selected.path)
                lines = [
                    f"{preset_id}: {'valid' if result.valid else 'invalid'}",
                    f"steps: {result.step_count}",
                ]
                lines.extend(f"  error: {error}" for error in result.errors)
                lines.extend(f"  warning: {warning}" for warning in result.warnings)
                body.update("\n".join(lines))
            elif button_id == "plan-preset":
                plan = self.services.plan_preset(preset_id)
                lines = [
                    f"{plan.name} v{plan.version}",
                    f"{len(plan.steps)} step(s):",
                ]
                lines.extend(
                    f"  [{step.type}] {step.id}" + (f" -> {step.action}" if step.action else "")
                    for step in plan.steps
                )
                if plan.input_requests:
                    lines.append("inputs needed: " + ", ".join(plan.input_requests))
                body.update("\n".join(lines))
        except Exception as exc:  # pragma: no cover - surfaced to operator
            body.update(f"Preset operation failed: {exc}")

    def _open_save_dialog(self) -> None:
        preset_id = self.selected_preset_id()
        if preset_id is None:
            self.query_one("#presets-body", Static).update("Select a preset to save first.")
            return
        self.workspace.push_screen(
            InputFormModal(
                f"Save a copy of {preset_id}",
                [
                    ("id", "New preset id (namespaced)", True),
                    ("name", "Display name (optional)", False),
                ],
                submit_label="Save",
            ),
            lambda values: self._handle_save(preset_id, values),
        )

    def _handle_save(self, source_id: str, values: dict[str, str] | None) -> None:
        if not values:
            return
        new_id = values.get("id", "").strip()
        if not new_id:
            return
        name = values.get("name", "").strip() or None
        body = self.query_one("#presets-body", Static)
        try:
            saved: PresetSaveDTO = self.services.save_preset(source_id, new_id=new_id, name=name)
        except Exception as exc:  # pragma: no cover - surfaced to operator
            body.update(f"Could not save preset: {exc}")
            return
        body.update(f"Saved {saved.id} to {saved.path}")
        self.call_after_refresh(self.safe_refresh)

    async def refresh_view(self) -> None:
        body = self.query_one("#presets-body", Static)
        preset_list = self.query_one("#presets-list", ListView)
        await preset_list.clear()
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
            await preset_list.append(ListItem(Static(label), id=preset.id))
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
