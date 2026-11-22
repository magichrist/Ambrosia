"""Input form modal: one line per input, secret inputs masked."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from ambrosia.tui.ids import safe_widget_id

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Key


class InputFormModal(ModalScreen[dict[str, str] | None]):
    """Collect one value per declared input.

    ``fields`` is a list of ``(field_id, label, required, secret)`` tuples, so
    the same modal serves both runtime command inputs and command definition
    forms. ``initial`` pre-fills values (e.g. from session state).
    """

    CSS = """
    Screen {
        align: center middle;
    }
    #input-form-dialog {
        width: 64;
        height: auto;
        max-height: 85%;
        background: #0d0714;
        border: round #ff5fa2;
        padding: 1 2;
    }
    #input-form-title {
        text-style: bold;
        color: #ffb454;
        text-align: center;
        height: 1;
        margin-bottom: 1;
    }
    .field-group {
        height: auto;
        margin-bottom: 1;
    }
    .field-group Label {
        height: 1;
    }
    .field-group Input {
        height: 3;
    }
    .hint {
        color: #ff8fc8;
        text-style: italic;
        height: 1;
    }
    #input-form-actions {
        height: auto;
        width: 100%;
        content-align: right middle;
        margin-top: 1;
    }
    #input-form-actions Button {
        width: auto;
        margin-left: 1;
    }
    #input-form-actions .spacer {
        width: 1fr;
    }
    """

    def __init__(
        self,
        title: str,
        fields: list[tuple[str, str, bool, bool]],
        *,
        initial: dict[str, str] | None = None,
        submit_label: str = "Run",
        hints: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.styles.align = ("center", "middle")
        self._title = title
        self._fields = list(fields)
        self._initial = dict(initial or {})
        self._submit_label = submit_label
        self._hints = dict(hints or {})
        self._widgets: dict[str, Input] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="input-form-dialog"):
            yield Label(self._title, id="input-form-title")
            for field_id, label, required, secret in self._fields:
                # Group each field so there is clear visual separation between
                # fields; required fields carry a bold red marker, optional
                # fields a dim "(optional)" marker.
                with Vertical(classes="field-group"):
                    if required:
                        marker = " [b][red]*[/red][/b]"
                    else:
                        marker = " [dim](optional)[/dim]"
                    widget_id = safe_widget_id(f"input-{field_id}")
                    yield Label(f"{label}{marker}", id=safe_widget_id(f"label-{field_id}"))
                    widget = Input(
                        value=self._initial.get(field_id, ""),
                        id=widget_id,
                        password=secret,
                    )
                    self._widgets[field_id] = widget
                    yield widget
                    hint = self._hints.get(field_id)
                    if hint:
                        yield Label(hint, id=safe_widget_id(f"hint-{field_id}"), classes="hint")
            with Horizontal(id="input-form-actions"):
                yield Static(classes="spacer")
                yield Button(self._submit_label, id="submit", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        # Focus the first field so typing works immediately; fall back to the
        # submit button for a form with no inputs.
        if self._widgets:
            next(iter(self._widgets.values())).focus()
        else:
            self.query_one("#submit", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        self._submit()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Enter on any field submits the form (not just the last field).
        self._submit()

    def _submit(self) -> None:
        values = {field_id: widget.value for field_id, widget in self._widgets.items()}
        self.dismiss(values)


__all__ = ["InputFormModal"]
