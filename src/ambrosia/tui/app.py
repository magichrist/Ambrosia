"""Ambrosia v2 TUI application: the primary command-launcher interface.

Layout (single screen, regions toggled with CSS classes):

* top bar          - app name, session, command count, running jobs, [q]uit
* search bar       - live, debounced filtering; ``r`` toggles regex
* results + preview- left results list, right preview of the highlighted command
* execution view   - shown while a job runs; hidden again with ``b``

The app depends only on the :mod:`ambrosia.v2` adapters (model, storage,
session, executor) and never on the v1 TUI.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from ambrosia.executor import (
    CommandResult,
    ExecutableNotFoundError,
    ShellExecutor,
    build_argv,
)
from ambrosia.model import Command
from ambrosia.session import SessionState, SessionStore
from ambrosia.storage import (
    add_command,
    load_commands,
    remove_command,
    save_commands,
)
from ambrosia.tui.widgets.execution_view import ExecutionView
from ambrosia.tui.widgets.input_form import InputFormModal
from ambrosia.tui.widgets.preview import PreviewPanel
from ambrosia.tui.widgets.results import ResultsList
from ambrosia.tui.widgets.search import SearchBar

if TYPE_CHECKING:
    from textual.events import Key

SESSION_FILE = Path.home() / ".ambrosia" / "session.json"


def _searchable_text(command: Command) -> str:
    """Concatenated name + description + tags + shell used for matching."""
    return " ".join([command.name, command.description, " ".join(command.tags), command.shell])


class AmbrosiaApp(App[None]):
    """The v2 Textual application."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #top-bar {
        dock: top;
        height: 3;
        padding: 0 1;
        color: $text;
        background: $panel;
    }
    #search-bar {
        height: 3;
        padding: 0 1;
        background: $surface;
    }
    #search-status {
        height: 1;
        padding: 0 1;
        color: #ff6666;
    }
    #main-split {
        height: 1fr;
        layout: horizontal;
    }
    #results {
        width: 1fr;
        border-right: solid $primary;
    }
    #preview {
        width: 56;
        background: $panel;
    }
    #execution-view {
        display: none;
    }
    #execution-view.visible {
        display: block;
        height: 1fr;
    }
    #main-split.hidden,
    #top-bar.hidden,
    #search-bar.hidden {
        display: none;
    }
    """

    BINDINGS = [
        Binding("/", "focus_search", "Search", show=True),
        Binding("tab", "focus_next", "Next region", show=True),
        Binding("enter", "select", "Select / run", show=True),
        Binding("escape", "go_back", "Clear / back", show=True),
        Binding("r", "toggle_regex", "Regex", show=True),
        Binding("n", "add_command", "New command", show=True),
        Binding("e", "edit_command", "Edit command", show=True),
        Binding("d", "delete_command", "Delete command", show=True),
        Binding("s", "save_session", "Save session", show=True),
        Binding("c", "cancel_job", "Cancel job", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
    ]

    commands: reactive[list[Command]] = reactive([])
    search_query: reactive[str] = reactive("")
    regex_mode: reactive[bool] = reactive(False)
    filtered: reactive[list[Command]] = reactive([])
    selected_command: reactive[Command | None] = reactive(None)
    running: reactive[bool] = reactive(False)
    execution_visible: reactive[bool] = reactive(False)
    regex_error: reactive[str | None] = reactive(None)

    def __init__(self, commands: list[Command] | None = None) -> None:
        super().__init__()
        self.session = SessionState()
        self.session_store = SessionStore(SESSION_FILE)
        self.executor = ShellExecutor()
        self._startup_commands = list(commands) if commands is not None else None
        self._run_task: asyncio.Task[None] | None = None
        self._search_debounce_task: asyncio.Task[None] | None = None
        self._filter_task: asyncio.Task[None] | None = None
        self._last_command: Command | None = None
        self._last_values: dict[str, str] = {}

    # ------------------------------------------------------------------ compose

    def compose(self) -> ComposeResult:
        yield Static(id="top-bar")
        yield SearchBar(id="search-bar")
        yield Static(id="search-status")
        yield Horizontal(
            ResultsList(id="results"),
            PreviewPanel(id="preview"),
            id="main-split",
        )
        yield ExecutionView(id="execution-view")

    # ------------------------------------------------------------------ mount

    def on_mount(self) -> None:
        self.session = self.session_store.load()
        if self._startup_commands is not None:
            self.commands = self._startup_commands
        else:
            try:
                self.commands = load_commands()
            except Exception:  # pragma: no cover - storage failure fallback
                self.commands = []
        self._recompute_filtered()
        self._refresh_top_bar()
        self.query_one("#search-bar", SearchBar).focus_input()

    # ------------------------------------------------------------------ reactive watchers

    def watch_search_query(self, _query: str) -> None:
        self._recompute_filtered()

    def watch_regex_mode(self, _regex_mode: bool) -> None:
        self._recompute_filtered()
        self.query_one("#search-bar", SearchBar).set_regex_mode(self.regex_mode)

    def watch_regex_error(self, error: str | None) -> None:
        status = self.query_one("#search-status", Static)
        if error:
            status.update(error)
        else:
            status.update("")

    def watch_filtered(self, filtered: list[Command]) -> None:
        if self.selected_command is not None:
            ids = {command.id for command in filtered}
            if self.selected_command.id not in ids:
                self.selected_command = None
        results = self.query_one("#results", ResultsList)
        if self._filter_task is not None:
            self._filter_task.cancel()
        self._filter_task = asyncio.create_task(results.set_commands(filtered))

    def watch_selected_command(self, command: Command | None) -> None:
        preview = self.query_one("#preview", PreviewPanel)
        preview.set_command(command, self.session)

    def watch_running(self, _running: bool) -> None:
        self._refresh_top_bar()

    def watch_execution_visible(self, visible: bool) -> None:
        top_bar = self.query_one("#top-bar", Static)
        search_bar = self.query_one("#search-bar", SearchBar)
        main_split = self.query_one("#main-split", Horizontal)
        execution = self.query_one("#execution-view", ExecutionView)
        if visible:
            top_bar.add_class("hidden")
            search_bar.add_class("hidden")
            main_split.add_class("hidden")
            execution.remove_class("hidden")
            execution.add_class("visible")
            execution.focus_log()
        else:
            execution.remove_class("visible")
            execution.add_class("hidden")
            top_bar.remove_class("hidden")
            search_bar.remove_class("hidden")
            main_split.remove_class("hidden")
            self.call_after_refresh(self.action_focus_results)

    # ------------------------------------------------------------------ helpers

    def _recompute_filtered(self) -> None:
        self.filtered = self._build_filtered()

    def _build_filtered(self) -> list[Command]:
        query = self.search_query
        if not query:
            self.regex_error = None
            return list(self.commands)
        if self.regex_mode:
            try:
                pattern = re.compile(query)
            except re.error as exc:
                self.regex_error = f"invalid regex: {exc}"
                return list(self.commands)
            self.regex_error = None
            return [
                command for command in self.commands if pattern.search(_searchable_text(command))
            ]
        self.regex_error = None
        needle = query.lower()
        return [command for command in self.commands if needle in _searchable_text(command).lower()]

    def _refresh_top_bar(self) -> None:
        bar = self.query_one("#top-bar", Static)
        running_count = 1 if self.running else 0
        bar.update(
            f"Ambrosia v2  [session: default]  [commands: {len(self.commands)}]  "
            f"[running: {running_count}]  [q]uit"
        )

    # ------------------------------------------------------------------ message handlers

    def on_command_highlighted(self, event: ResultsList.CommandHighlighted) -> None:
        self.selected_command = event.command
        event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Debounce search input changes and apply them to the catalog filter."""
        if event.input.id != "search-bar":
            return
        if self._search_debounce_task is not None:
            self._search_debounce_task.cancel()
        self._search_debounce_task = asyncio.create_task(self._emit_search())

    async def _emit_search(self) -> None:
        try:
            await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return
        search = self.query_one("#search-bar", SearchBar)
        self.search_query = search.value

    def on_execution_view_command_finished(self, event: ExecutionView.CommandFinished) -> None:
        pass

    # ------------------------------------------------------------------ actions

    def action_focus_search(self) -> None:
        self.query_one("#search-bar", SearchBar).focus_input()

    def action_focus_results(self) -> None:
        self.query_one("#results", ResultsList).focus()

    def action_toggle_regex(self) -> None:
        if self.execution_visible:
            return
        self.regex_mode = not self.regex_mode

    async def action_select(self) -> None:
        search = self.query_one("#search-bar", SearchBar)
        if search.has_focus:
            self.action_focus_results()
            return
        if self.execution_visible:
            if self._last_command is not None:
                await self._run_command(self._last_command, self._last_values)
            return
        results = self.query_one("#results", ResultsList)
        command = results.selected_command()
        if command is None:
            return
        self.selected_command = command
        self._resolve_and_run(command)

    def _resolve_and_run(self, command: Command) -> None:
        required_ids = [input_.id for input_ in command.required_inputs()]
        if self.session.has_all_required(command.id, required_ids):
            self._confirm_run(command)
        else:
            self._open_input_form(command)

    def _confirm_run(self, command: Command) -> None:
        values = self.session.get_all(command.id)
        argv = build_argv(command.shell, values)
        modal = _ConfirmRunModal(command, argv)
        self.push_screen(modal, lambda outcome: self._handle_confirm_run(outcome, command))

    def _handle_confirm_run(self, outcome: str | None, command: Command) -> None:
        if outcome == "run":
            asyncio.create_task(self._run_command(command, self.session.get_all(command.id)))
        elif outcome == "edit":
            self._open_input_form(command)

    def _open_input_form(self, command: Command) -> None:
        fields = [
            (input_.id, input_.prompt, input_.required, input_.secret) for input_ in command.inputs
        ]
        initial = self.session.get_all(command.id)
        modal = InputFormModal(
            f"Inputs for {command.name}",
            fields,
            initial=initial,
            submit_label="Run",
        )
        self.push_screen(modal, lambda values: self._handle_input_form(values, command))

    def _handle_input_form(self, values: dict[str, str] | None, command: Command) -> None:
        if values is None:
            return
        self.session.set_all(command.id, values)
        asyncio.create_task(self._run_command(command, values))

    async def _run_command(self, command: Command, values: dict[str, str]) -> None:
        self.session.set_all(command.id, values)
        argv = build_argv(command.shell, values)
        execution = self.query_one("#execution-view", ExecutionView)
        execution.start(command.name, argv)
        self.running = True
        self.execution_visible = True
        self._last_command = command
        self._last_values = dict(values)

        async def _run() -> None:
            try:
                result = await self.executor.run(command.shell, values, on_output=self._on_output)
            except ExecutableNotFoundError as exc:
                execution.write_line(str(exc))
                result = CommandResult(
                    exit_code=127,
                    duration_ms=0,
                    stdout="",
                    stderr="",
                    cancelled=False,
                )
            except asyncio.CancelledError:
                self.running = False
                self.execution_visible = False
                raise
            self.running = False
            execution.finish(result.exit_code, result.duration_ms)

        self._run_task = asyncio.create_task(_run())

    async def _on_output(self, text: str) -> None:
        self.query_one("#execution-view", ExecutionView).write_line(text)

    def action_cancel_job(self) -> None:
        if not self.running:
            return
        self.executor.cancel()
        if self._run_task is not None:
            self._run_task.cancel()

    def action_go_back(self) -> None:
        if self.execution_visible:
            self.execution_visible = False
        elif self.search_query:
            self.search_query = ""

    def action_add_command(self) -> None:
        if self.execution_visible:
            return
        fields = [
            ("id", "Command id", True, False),
            ("name", "Name", True, False),
            ("description", "Description", False, False),
            ("tags", "Tags (comma-separated)", False, False),
            ("shell", "Shell template ({{input_id}})", True, False),
        ]
        modal = InputFormModal("Add command", fields, submit_label="Add")
        self.push_screen(modal, self._handle_add_command)

    def _handle_add_command(self, values: dict[str, str] | None) -> None:
        if not values:
            return
        command_id = values.get("id", "").strip()
        name = values.get("name", "").strip()
        shell = values.get("shell", "").strip()
        if not command_id or not name or not shell:
            self.notify("id, name, and shell are required")
            return
        tags = [tag.strip() for tag in values.get("tags", "").split(",") if tag.strip()]
        command = Command(
            id=command_id,
            name=name,
            description=values.get("description", ""),
            tags=tags,
            shell=shell,
            inputs=[],
        )
        try:
            add_command(command)
        except ValueError as exc:
            self.notify(str(exc))
            return
        self.commands = [*self.commands, command]
        self._recompute_filtered()
        self.notify("command added")

    def action_edit_command(self) -> None:
        if self.execution_visible:
            return
        results = self.query_one("#results", ResultsList)
        command = results.selected_command()
        if command is None:
            return
        fields = [
            ("id", "Command id", True, False),
            ("name", "Name", True, False),
            ("description", "Description", False, False),
            ("tags", "Tags (comma-separated)", False, False),
            ("shell", "Shell template ({{input_id}})", True, False),
        ]
        initial = {
            "id": command.id,
            "name": command.name,
            "description": command.description,
            "tags": ", ".join(command.tags),
            "shell": command.shell,
        }
        modal = InputFormModal("Edit command", fields, initial=initial, submit_label="Save")
        self.push_screen(modal, lambda values: self._handle_edit_command(values, command))

    def _handle_edit_command(self, values: dict[str, str] | None, command: Command) -> None:
        if not values:
            return
        command_id = values.get("id", "").strip()
        name = values.get("name", "").strip()
        shell = values.get("shell", "").strip()
        if not command_id or not name or not shell:
            self.notify("id, name, and shell are required")
            return
        tags = [tag.strip() for tag in values.get("tags", "").split(",") if tag.strip()]
        updated = Command(
            id=command_id,
            name=name,
            description=values.get("description", ""),
            tags=tags,
            shell=shell,
            inputs=command.inputs,
        )
        self.commands = [
            updated if existing.id == command.id else existing for existing in self.commands
        ]
        try:
            save_commands(self.commands)
        except Exception as exc:  # noqa: BLE001 - surface storage failure
            self.notify(f"save failed: {exc}")
            return
        self._recompute_filtered()
        self.notify("command saved")

    def action_delete_command(self) -> None:
        if self.execution_visible:
            return
        results = self.query_one("#results", ResultsList)
        command = results.selected_command()
        if command is None:
            return
        modal = _ConfirmModal(f"Delete command {command.id}?", confirm_label="Delete")
        self.push_screen(
            modal,
            lambda confirmed: self._handle_delete_command(confirmed, command),
        )

    def _handle_delete_command(self, confirmed: bool | None, command: Command) -> None:
        if not confirmed:
            return
        remove_command(command.id)
        self.commands = [existing for existing in self.commands if existing.id != command.id]
        self._recompute_filtered()
        self.notify("command deleted")

    def action_save_session(self) -> None:
        self.session_store.save(self.session)
        self.notify("session saved")

    def action_quit_app(self) -> None:
        if self.running:
            modal = _ConfirmModal("Quit with a job still running?", confirm_label="Quit")
            self.push_screen(modal, self._handle_quit_confirm)
        else:
            self._save_and_exit()

    def _handle_quit_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self._save_and_exit()

    def _save_and_exit(self) -> None:
        self.session_store.save(self.session)
        self.exit()

    def action_help(self) -> None:
        self.push_screen(_HelpModal())


class _ConfirmModal(ModalScreen[bool]):
    """Ask the operator to confirm an action (e.g. delete, quit while running)."""

    def __init__(self, message: str, *, confirm_label: str = "Yes") -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._message, id="confirm-message")
            with Horizontal():
                yield Button(self._confirm_label, id="confirm", variant="primary")
                yield Button("No", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(False)
            event.prevent_default()
            event.stop()


class _ConfirmRunModal(ModalScreen[str | None]):
    """Confirm running a command with saved values; outcomes: "run", "edit", None."""

    def __init__(self, command: Command, argv: list[str]) -> None:
        super().__init__()
        self._command = command
        self._argv = argv

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(
                f"Run `{' '.join(self._argv)}`? (saved values)",
                id="confirm-message",
            )
            with Horizontal():
                yield Button("Run", id="run", variant="primary")
                yield Button("Edit inputs", id="edit")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "run":
            self.dismiss("run")
        elif button_id == "edit":
            self.dismiss("edit")
        else:
            self.dismiss(None)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()


class _HelpModal(ModalScreen[None]):
    """Keyboard reference."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Ambrosia v2 — keyboard reference", id="title")
            yield Static(
                "/      focus search bar and filter\n"
                "Tab    move focus between search and results\n"
                "Enter  select highlighted command / run\n"
                "Esc    clear search / close modal / back\n"
                "r      toggle regex mode\n"
                "n      add a new command\n"
                "e      edit the selected command\n"
                "d      delete the selected command (confirm)\n"
                "s      save session inputs\n"
                "c      cancel the currently running job\n"
                "b      back from the execution view (job keeps running)\n"
                "q      quit (confirm if a job is running)\n"
                "?      show this help\n",
                id="help-text",
            )
            yield Button("Close", id="close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss()
            event.prevent_default()
            event.stop()


__all__ = ["AmbrosiaApp"]
