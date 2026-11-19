"""Modal dialogs: confirmation, help, and input collection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.events import Key


class ConfirmDialog(ModalScreen[bool]):
    """Ask the operator to confirm an action (e.g. quit with active jobs)."""

    def __init__(self, message: str, *, confirm_label: str = "Yes") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._message, id="message")
            with Horizontal():
                yield Button(self._confirm_label, id="confirm", variant="primary")
                yield Button("No", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)


class HelpModal(ModalScreen[None]):
    """Keyboard reference."""

    DEFAULT_CSS = """
    HelpModal > Vertical {
        width: 70;
        height: 22;
        background: $panel;
        padding: 1 2;
    }
    HelpModal Static {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Ambrosia — keyboard reference", id="title")
            yield Static(
                "/   global search / command palette\n"
                "Tab move between regions (context, content, activity)\n"
                "Enter open / select\n"
                "Esc   back / close modal\n"
                "g   engagement switcher\n"
                "?   show this help\n"
                "q   quit (confirm if jobs are active)\n",
                id="help-text",
            )
            yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()


class DetailModal(ModalScreen[None]):
    """Read-only detail view for a job, artifact, or finding."""

    DEFAULT_CSS = """
    DetailModal > Vertical {
        width: 90;
        height: 24;
        background: $panel;
        padding: 1 2;
    }
    DetailModal Static#detail-text {
        height: 1fr;
        border: solid $primary;
        padding: 1;
    }
    """

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self._title = title
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, id="title")
            yield Static(self._text, id="detail-text")
            yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()


class InputFormModal(ModalScreen[dict[str, str] | None]):
    """Collect typed inputs for an action before execution.

    Fields whose names look like secrets (password, secret, token, key, etc.)
    are rendered as password inputs so the value is never echoed.
    """

    _SECRET_NAMES = frozenset(
        {"password", "passwd", "secret", "token", "key", "credential", "hash"}
    )

    def __init__(
        self,
        title: str,
        fields: list[tuple[str, str, bool]],
        *,
        submit_label: str = "Run",
    ) -> None:
        """``fields`` is a list of ``(name, label, required)`` tuples."""
        super().__init__()
        self._title = title
        self._fields = fields
        self._submit_label = submit_label

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title, id="title")
            for name, label, required in self._fields:
                marker = " *" if required else ""
                yield Label(f"{label}{marker}", id=f"label-{name}")
                secret = name.lower() in self._SECRET_NAMES
                yield Input(
                    placeholder=label,
                    id=f"input-{name}",
                    password=secret,
                )
            with Horizontal():
                yield Button(self._submit_label, id="submit", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        values: dict[str, str] = {}
        for name, _label, _required in self._fields:
            widget = self.query_one(f"#input-{name}", Input)
            values[name] = widget.value
        self.dismiss(values)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()


__all__ = ["ConfirmDialog", "HelpModal", "InputFormModal"]
