"""Preset explorer: ranked search results as compact, hoverable rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.message import Message
from textual.widgets import ListItem, ListView, Static

from ambrosia.model import Command
from ambrosia.tui.design import GUMMY_LIGHT_PINK, GUMMY_PINK, PHOSPHOR, TEXT_MUTED
from ambrosia.tui.ids import safe_widget_id
from ambrosia.workflow import Workflow

if TYPE_CHECKING:
    from ambrosia.tui.matching import SearchResult

ExplorerItem = Command | Workflow


class PresetExplorer(ListView):
    """A list of matching presets and workflows; the highlighted row feeds the inspector."""

    class ItemHighlighted(Message):
        """Posted when a different result row is highlighted."""

        def __init__(self, item: ExplorerItem) -> None:
            super().__init__()
            self.item = item

    class ItemActivated(Message):
        """Posted when Enter is pressed on a result row."""

        def __init__(self, item: ExplorerItem) -> None:
            super().__init__()
            self.item = item

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._results: list[SearchResult] = []
        self._items: dict[str, ExplorerItem] = {}
        self._item_counter = 0

    async def set_results(self, results: list[SearchResult]) -> None:
        """Replace the displayed results with ranked matches."""
        self._results = list(results)
        self._items = {}
        self._item_counter = 0
        await self.clear()
        for result in results:
            item = result.item
            kind = "workflow" if isinstance(item, Workflow) else "preset"
            # Unique widget ids: different directories may reuse an id, and
            # duplicate ids raise DuplicateIds in Textual.
            item_id = safe_widget_id(f"{kind}_{item.name}_{self._item_counter}")
            self._item_counter += 1
            self._items[item_id] = item
            await self.append(self._make_item(item, item_id))
        # Highlight the best match so the inspector is populated and Enter can
        # work immediately without requiring an initial arrow key.
        self.index = 0 if results else None

    def _make_item(self, item: ExplorerItem, item_id: str) -> ListItem:
        if isinstance(item, Workflow):
            label = Text()
            label.append(item.name, style=f"bold {GUMMY_PINK}")
            label.append(" [workflow] ", style=f"bold {GUMMY_LIGHT_PINK}")
            label.append(": ", style=TEXT_MUTED)
            label.append(
                f"{len(item.phase_names())} phases, {item.command_count()} commands",
                style=TEXT_MUTED,
            )
            tooltip = self._workflow_tooltip(item)
        else:
            # Compact row: just "name: description". Full detail lives in the
            # inspector and in the hover tooltip.
            label = Text()
            label.append(item.name, style=f"bold {PHOSPHOR}")
            label.append(": ", style=TEXT_MUTED)
            label.append(item.description or item.shell or item.id, style=TEXT_MUTED)
            tooltip = self._command_tooltip(item)
        row = ListItem(Static(label), id=item_id)
        row.tooltip = tooltip
        return row

    @staticmethod
    def _command_tooltip(command: Command) -> Text:
        """Build the full-detail text shown when hovering a preset row."""
        tip = Text()
        tip.append(command.name, style="bold")
        tip.append(f"\nid: {command.id}", style=TEXT_MUTED)
        if command.category:
            tip.append(f"\npath: {command.category}", style=TEXT_MUTED)
        if command.tags:
            tip.append(f"\ntags: {', '.join(command.tags)}", style=TEXT_MUTED)
        tip.append("\n\nshell:", style="bold")
        tip.append(f"\n{command.shell}", style=PHOSPHOR)
        if command.inputs:
            tip.append("\n\ninputs:", style="bold")
            for input_ in command.inputs:
                required = " *" if input_.required else ""
                secret = " (secret)" if input_.secret else ""
                tip.append(f"\n  [{input_.id}]{required}{secret} {input_.prompt}", style=TEXT_MUTED)
        return tip

    @staticmethod
    def _workflow_tooltip(workflow: Workflow) -> Text:
        """Build the full-detail text shown when hovering a workflow row."""
        tip = Text()
        tip.append(workflow.name, style="bold")
        tip.append(f"\nid: {workflow.id}", style=TEXT_MUTED)
        if workflow.description:
            tip.append(f"\n\n{workflow.description}", style=TEXT_MUTED)
        for phase in workflow.phase_names():
            tip.append(f"\n\n{phase}:", style=f"bold {GUMMY_PINK}")
            for command_id in workflow.command_ids(phase):
                tip.append(f"\n  {command_id}", style=TEXT_MUTED)
        return tip

    def selected_item(self) -> ExplorerItem | None:
        """Return the highlighted item, or ``None`` when nothing is selected."""
        item = self.highlighted_child
        if item is None or item.id is None:
            return None
        return self._items.get(item.id)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or event.item.id is None:
            return
        item = self._items.get(event.item.id)
        if item is not None:
            self.post_message(self.ItemHighlighted(item))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Translate ListView's Enter into an explicit item activation."""
        if event.item is None or event.item.id is None:
            return
        item = self._items.get(event.item.id)
        if item is not None:
            self.post_message(self.ItemActivated(item))
        event.stop()


__all__ = ["ExplorerItem", "PresetExplorer"]
