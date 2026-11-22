"""Tag sidebar: checkbox filters with AND/OR matching mode."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.containers import VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Checkbox, Label, RadioButton, RadioSet

from ambrosia.tui.design import GUMMY_PINK, PHOSPHOR, TEXT_MUTED
from ambrosia.tui.ids import safe_widget_id

if TYPE_CHECKING:
    from textual.app import ComposeResult


class TagBrowser(Widget):
    """Checkbox list of tags with an OR/AND toggle."""

    CSS = f"""
    TagBrowser {{
        height: 1fr;
        padding: 0 1;
    }}
    #tag-title {{
        color: {GUMMY_PINK};
        text-style: bold;
        height: 1;
    }}
    #tag-mode {{
        height: auto;
        margin-bottom: 1;
    }}
    #tag-mode RadioButton {{
        color: {TEXT_MUTED};
    }}
    #tag-mode RadioButton:checked {{
        color: {PHOSPHOR};
    }}
    .tag-row {{
        height: 1;
    }}
    .tag-row:checked {{
        color: {PHOSPHOR};
    }}
    """

    class TagsChanged(Message):
        """Posted when the selected tags or match mode changes."""

        def __init__(self, tags: list[str], mode: str) -> None:
            super().__init__()
            self.tags = tags
            self.mode = mode

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._tag_checkboxes: dict[str, Checkbox] = {}
        self._id_to_tag: dict[str, str] = {}
        self._mode = "or"
        # Removing and re-mounting checkboxes is async; serialize refresh calls
        # so quick successive updates cannot collide on duplicate widget ids.
        self._refresh_lock = asyncio.Lock()

    def compose(self) -> ComposeResult:
        yield Label("TAGS", id="tag-title")
        with RadioSet(id="tag-mode"):
            yield RadioButton("OR (any)", id="tag-mode-or", value=True)
            yield RadioButton("AND (all)", id="tag-mode-and")
        yield VerticalScroll(id="tag-list")

    def set_tags(self, tag_counts: dict[str, int], active_tags: list[str] | None = None) -> None:
        """Populate the tag list from ``tag_counts`` (tag -> preset count)."""
        asyncio.create_task(self._apply_tags(dict(tag_counts), list(active_tags or [])))

    async def _apply_tags(self, tag_counts: dict[str, int], active_tags: list[str]) -> None:
        async with self._refresh_lock:
            container = self.query_one("#tag-list", VerticalScroll)
            await container.remove_children()
            self._tag_checkboxes = {}
            self._id_to_tag = {}
            for tag, count in sorted(tag_counts.items()):
                widget_id = safe_widget_id(f"tag-{tag}")
                checkbox = Checkbox(
                    f"{tag}  [{count}]",
                    id=widget_id,
                    value=tag in active_tags,
                    classes="tag-row",
                )
                self._tag_checkboxes[tag] = checkbox
                self._id_to_tag[widget_id] = tag
                await container.mount(checkbox)

    def set_mode(self, mode: str) -> None:
        """Set the tag match mode ("and" or "or")."""
        self._mode = mode

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if str(event.checkbox.id or "") in self._id_to_tag:
            self._emit()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.pressed is not None:
            self._mode = "and" if event.pressed.id == "tag-mode-and" else "or"
        self._emit()

    def _emit(self) -> None:
        selected = [tag for tag, box in self._tag_checkboxes.items() if box.value]
        self.post_message(self.TagsChanged(selected, self._mode))


__all__ = ["TagBrowser"]
