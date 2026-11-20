"""Action details view: inspect an action and run it with collected inputs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Button, Input, Label, Static

from ambrosia.tui.views.base import BaseView
from ambrosia.tui.widgets.modals import InputFormModal

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.application.action_service import ActionCheckDTO, ActionDTO
    from ambrosia.tui.services import TUIServiceAdapter


class ActionDetailsView(BaseView):
    """Show action metadata, availability (with reasons), and run controls."""

    def __init__(
        self,
        services: TUIServiceAdapter,
        action_id: str,
        id: str | None = None,
    ) -> None:
        super().__init__(services, id=id)
        self._action_id = action_id
        self._dto: ActionDTO | None = None
        self._check: ActionCheckDTO | None = None
        self._typed_inputs: dict[str, object] = {}

    def compose(self) -> ComposeResult:
        yield Static(id="details-header")
        yield Static(id="details-body")
        yield Label("Inputs", id="inputs-title")
        yield Input(placeholder="key=value,key2=value2", id="details-inputs")
        with Vertical():
            yield Button("Run", id="run-action", variant="primary")
            yield Button("Dry run (preview)", id="dry-run-action")
            yield Button("Typed inputs...", id="typed-inputs")
            yield Button("Back", id="back-action")

    def on_mount(self) -> None:
        # Defer until composed children are available in the DOM.
        self.call_after_refresh(self.safe_refresh)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "back-action":
            self.workspace.action_go_back()
            return
        if button_id == "typed-inputs":
            self._open_typed_inputs()
            return
        inputs = self._collect_inputs()
        if button_id == "run-action":
            self.workspace.execute_action(self._action_id, inputs)
            self.workspace.status_bar().set_status(f"queued {self._action_id}")
        elif button_id == "dry-run-action":
            self.workspace.dry_run_action(self._action_id, inputs)

    def _collect_inputs(self) -> dict[str, object]:
        """Prefer typed form values; fall back to the free-form key=value field."""
        if self._typed_inputs:
            return dict(self._typed_inputs)
        return self.workspace.parse_inputs(
            self.query_one("#details-inputs", Input).value
        )

    def _open_typed_inputs(self) -> None:
        definition = self.services.action_definition(self._action_id)
        schema = definition.input_schema if definition is not None else {}
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        raw_required = schema.get("required", []) if isinstance(schema, dict) else []
        required = set(raw_required) if isinstance(raw_required, (list, tuple)) else set()
        fields: list[tuple[str, str, bool]] = []
        if isinstance(properties, dict):
            for name, prop in properties.items():
                label = name
                if isinstance(prop, dict):
                    label = str(prop.get("title") or prop.get("description") or name)
                fields.append((name, label, name in required))
        if not fields:
            self.workspace.push_screen(
                InputFormModal(self._action_id, [("value", "Value", False)], submit_label="Save"),
                self._handle_typed_inputs,
            )
            return
        self.workspace.push_screen(
            InputFormModal(self._action_id, fields, submit_label="Save"),
            self._handle_typed_inputs,
        )

    def _handle_typed_inputs(self, values: dict[str, str] | None) -> None:
        if values is None:
            return
        self._typed_inputs = {key: value for key, value in values.items() if value != ""}
        summary = ", ".join(self._typed_inputs) or "(none)"
        self.query_one("#details-header", Static).update(
            f"{self._action_id} — inputs: {summary}"
        )

    async def refresh_view(self) -> None:
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        target_address = getattr(app, "current_target_address", None) or None

        header = self.query_one("#details-header", Static)
        body = self.query_one("#details-body", Static)
        if not engagement_id:
            header.update("No engagement selected")
            body.update("Open an engagement to view and run actions.")
            return
        try:
            self._dto = self.services.get_action(self._action_id)
            self._check = self.services.check_action(
                self._action_id,
                engagement_id=engagement_id,
                target_address=target_address,
            )
        except Exception as exc:  # pragma: no cover - services unavailable
            header.update(f"Action {self._action_id}")
            body.update(f"Unable to load action: {exc}")
            return

        dto = self._dto
        check = self._check
        if dto is None or check is None:
            header.update(f"Action {self._action_id}")
            body.update("Action details are unavailable.")
            return
        header.update(
            f"{dto.id}  (v{dto.version})  |  {dto.category}  |  risk: {dto.risk}  |  "
            f"executor: {dto.executor_kind}"
        )
        lines = [dto.description or ""]
        lines.append("")
        lines.append(f"availability: {check.status}")
        lines.append(f"allowed: {'yes' if check.allowed else 'no'}")
        if check.reasons:
            lines.append("reasons:")
            for reason in check.reasons:
                lines.append(f"  - {reason}")
        if check.missing_inputs:
            lines.append("missing inputs: " + ", ".join(check.missing_inputs))
        if check.matched_artifact_ids:
            lines.append("matched artifacts: " + ", ".join(check.matched_artifact_ids))
        if check.required_approval:
            lines.append("approval required: yes")
        if dto.effects:
            lines.append(f"effects: {', '.join(dto.effects)}")
        if dto.scope_fields:
            lines.append(f"scope fields: {', '.join(dto.scope_fields)}")
        if dto.dependencies:
            lines.append(f"dependencies: {', '.join(dto.dependencies)}")
        lines.append("")
        lines.append("why: " + self._why(check))
        body.update("\n".join(lines))

    @staticmethod
    def _why(check: ActionCheckDTO) -> str:
        if check.allowed:
            return "all requirements satisfied; the action can run now."
        if check.status == "needs_input":
            return "applicable, but required operator inputs are missing."
        if check.status == "needs_approval":
            return "applicable, but policy requires explicit approval before running."
        if check.status == "blocked":
            return "blocked by scope or policy; see reasons above."
        if check.status == "missing_dependency":
            return "a required local tool or runtime is not installed."
        if check.status == "not_applicable":
            return "required context (artifact / platform / target) is absent."
        return "unavailable."


__all__ = ["ActionDetailsView"]
