"""Ambrosia v2 TUI application: the primary command-launcher interface.

Layout (single screen, regions toggled with CSS classes):

* top bar (dock top)      - app name, session status, command count, running jobs,
                             category / scope / history indicators, [q]uit
* search bar (dock top)   - live, debounced filtering
* mode indicator          - current search mode (substring / fuzzy / regex)
* search status           - errors (e.g. invalid regex)
* results + preview       - left results list, right preview of the highlighted command
* execution view          - shown while a job runs; hidden again with ``b``
* footer (dock bottom)    - compact key-binding summary

The app depends only on the :mod:`ambrosia.v2` adapters (model, storage,
session, executor) and never on the v1 TUI.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
from dataclasses import replace
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
from ambrosia.history import HistoryStore, make_entry
from ambrosia.model import Command
from ambrosia.scope import ScopePolicy, check_target, load_scope_policy, save_scope_policy
from ambrosia.session import SessionState, SessionStore
from ambrosia.storage import (
    add_command,
    export_commands,
    get_categories,
    get_favorites,  # noqa: F401  -- part of the storage integration surface
    get_pinned,  # noqa: F401  -- part of the storage integration surface
    import_commands,
    load_commands,
    remove_command,
    save_commands,
)
from ambrosia.tui.widgets.execution_view import ExecutionView
from ambrosia.tui.widgets.input_form import InputFormModal
from ambrosia.tui.widgets.preview import PreviewPanel
from ambrosia.tui.widgets.results import ResultsList
from ambrosia.tui.widgets.search import SearchBar, SearchMode

if TYPE_CHECKING:
    from textual.events import Key

SESSION_FILE = Path.home() / ".ambrosia" / "session.json"


def _searchable_text(command: Command) -> str:
    """Concatenated name + description + tags + shell used for matching."""
    return " ".join([command.name, command.description, " ".join(command.tags), command.shell])


def _fuzzy_score(query: str, text: str) -> int | None:
    """Score ``query`` as a character subsequence of ``text`` (case-insensitive).

    Returns the length of the match span (first to last matched character,
    inclusive) when every character of ``query`` appears in order in
    ``text``, or ``None`` when it is not a subsequence. Shorter spans are
    better matches.
    """
    query = query.lower()
    text = text.lower()
    start: int | None = None
    index = 0
    for char in query:
        found = text.find(char, index)
        if found == -1:
            return None
        if start is None:
            start = found
        index = found + 1
    if start is None:
        return None
    return index - start


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
        layout: horizontal;
    }
    #top-bar-left {
        width: 1fr;
    }
    #top-bar-right {
        width: auto;
        content-align: right middle;
    }
    #search-bar {
        height: 3;
        padding: 0 1;
        background: $surface;
        border-bottom: solid $panel;
    }
    #search-mode-indicator {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }
    #search-status {
        height: 1;
        padding: 0 1;
        color: $error;
    }
    #main-split {
        height: 1fr;
        layout: horizontal;
    }
    #results {
        width: 1fr;
        border-right: solid $primary;
        padding: 0 1;
    }
    #preview {
        width: 56;
        background: $surface;
        border-left: solid $panel;
        padding: 0 1;
    }
    #execution-view {
        display: none;
    }
    #execution-view.visible {
        display: block;
        height: 1fr;
        border-top: solid $primary;
    }
    #execution-header {
        height: 1;
        padding: 0 1;
        color: $text;
        background: $panel;
    }
    #execution-status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    #execution-log {
        height: 1fr;
        padding: 0 1;
    }
    #main-split.hidden,
    #top-bar.hidden,
    #search-bar.hidden {
        display: none;
    }
    .hint {
        color: $text-muted;
        text-style: italic;
        margin: 0 1 0 1;
    }
    .favorite-indicator {
        color: $warning;
    }
    .pinned-indicator {
        color: $accent;
    }
    .status-green {
        color: $success;
    }
    .status-red {
        color: $error;
    }
    .status-yellow {
        color: $warning;
    }
    #footer {
        dock: bottom;
        height: 3;
        padding: 0 1;
        color: $text;
        background: $panel;
    }
    """

    BINDINGS = [
        Binding("/", "focus_search", "Search", show=True),
        Binding("tab", "focus_next", "Next region", show=True),
        Binding("enter", "select", "Select / run", show=True),
        Binding("escape", "go_back", "Clear / back", show=True),
        Binding("r", "toggle_regex", "Mode", show=True),
        Binding("f", "cycle_search_mode", "Mode", show=True),
        Binding("n", "add_command", "New command", show=True),
        Binding("e", "edit_command", "Edit command", show=True),
        Binding("d", "delete_command", "Delete command", show=True),
        Binding("i", "import_commands", "Import commands", show=True),
        Binding("E", "export_commands", "Export commands", show=True),
        Binding("s", "save_session", "Save session", show=True),
        Binding("c", "cancel_job", "Cancel job", show=True),
        Binding("g", "run_again", "Run again", show=True),
        Binding("b", "go_back", "Back", show=True),
        Binding("q", "quit_app", "Quit", show=True),
        Binding("?", "help", "Help", show=True),
        Binding("]", "cycle_category_filter", "Category", show=True),
        Binding("F", "toggle_favorites", "Favorites", show=True),
        Binding("*", "toggle_favorite_on_selected", "Favorite", show=True),
        Binding("p", "toggle_pinned", "Pin", show=True),
        Binding("h", "toggle_history", "History", show=True),
        Binding("S", "toggle_scope", "Scope", show=True),
    ]

    # Debounce delay for live search filtering (seconds). Configurable by
    # subclassing or instance attribute override.
    SEARCH_DEBOUNCE_SECONDS: float = 0.075

    commands: reactive[list[Command]] = reactive([])
    search_query: reactive[str] = reactive("")
    search_mode: reactive[SearchMode] = reactive("substring")
    filtered: reactive[list[Command]] = reactive([])
    selected_command: reactive[Command | None] = reactive(None)
    running: reactive[bool] = reactive(False)
    execution_visible: reactive[bool] = reactive(False)
    regex_error: reactive[str | None] = reactive(None)
    category_filter: reactive[str] = reactive("")
    show_favorites_only: reactive[bool] = reactive(False)

    _session_dirty: bool = False
    _auto_save_task: asyncio.Task[None] | None = None
    scope_policy: ScopePolicy | None = None
    history_store: HistoryStore

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
        self._last_result: CommandResult | None = None
        self.history_store = HistoryStore()

    # ------------------------------------------------------------------ compose

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(id="top-bar-left"),
            Static(id="top-bar-right"),
            id="top-bar",
        )
        yield SearchBar(id="search-bar")
        yield Static(id="search-mode-indicator")
        yield Static(id="search-status")
        yield Horizontal(
            ResultsList(id="results"),
            PreviewPanel(id="preview"),
            id="main-split",
        )
        yield ExecutionView(id="execution-view")
        yield Static(id="footer")

    # ------------------------------------------------------------------ mount

    def on_mount(self) -> None:
        self.session = self.session_store.load()
        self._session_dirty = False
        self._auto_save_task: asyncio.Task[None] | None = None
        self.session.on_change(self._on_session_changed)
        if self._startup_commands is not None:
            self.commands = self._startup_commands
        else:
            try:
                self.commands = load_commands()
            except Exception:  # pragma: no cover - storage failure fallback
                self.commands = []
        # Remember which inputs are secret so they are excluded from the
        # persisted session file (SessionStore.save excludes secrets by default).
        for command in self.commands:
            secret_ids = {input_.id for input_ in command.inputs if input_.secret}
            if secret_ids:
                self.session.register_secret_inputs(command.id, secret_ids)
        self.scope_policy = load_scope_policy()
        self.history_store = HistoryStore()
        self._recompute_filtered()
        self._refresh_top_bar()
        self._refresh_mode_indicator()
        self._refresh_footer()
        self.query_one("#search-bar", SearchBar).focus_input()

    # ------------------------------------------------------------------ reactive watchers

    def watch_search_query(self, _query: str) -> None:
        self._recompute_filtered()

    def watch_search_mode(self, _mode: SearchMode) -> None:
        self._recompute_filtered()
        self.query_one("#search-bar", SearchBar).set_search_mode(self.search_mode)
        self._refresh_mode_indicator()
        if self.search_mode != "regex":
            # Switching away from regex mode clears any stale regex error.
            self.regex_error = None

    def watch_category_filter(self, _filter: str) -> None:
        self._recompute_filtered()

    def watch_show_favorites_only(self, _show: bool) -> None:
        self._recompute_filtered()

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
        top_bar = self.query_one("#top-bar", Horizontal)
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
            base: list[Command] = list(self.commands)
        elif self.search_mode == "regex":
            try:
                pattern = re.compile(query)
            except re.error as exc:
                self.regex_error = f"invalid regex: {exc}"
                base = list(self.commands)
            else:
                self.regex_error = None
                base = [
                    command
                    for command in self.commands
                    if pattern.search(_searchable_text(command))
                ]
        elif self.search_mode == "fuzzy":
            self.regex_error = None
            needle = query.lower()
            scored: list[tuple[int, Command]] = []
            for command in self.commands:
                score = _fuzzy_score(needle, _searchable_text(command))
                if score is not None:
                    scored.append((score, command))
            scored.sort(key=lambda item: item[0])
            base = [command for _, command in scored]
        else:
            self.regex_error = None
            needle = query.lower()
            base = [
                command for command in self.commands if needle in _searchable_text(command).lower()
            ]

        # Category filter: keep only commands whose category matches.
        if self.category_filter:
            base = [command for command in base if command.category == self.category_filter]
        # Favorites-only filter: keep only favorited commands.
        if self.show_favorites_only:
            base = [command for command in base if command.favorite]
        # Pin pinned commands to the top, preserving relative order otherwise.
        base.sort(key=lambda command: not command.pinned)
        return base

    def _refresh_top_bar(self) -> None:
        left = self.query_one("#top-bar-left", Static)
        right = self.query_one("#top-bar-right", Static)
        running_count = 1 if self.running else 0
        session_status = "[green]saved[/]" if not self._session_dirty else "[red]unsaved[/]"
        running_text = f"[red]{running_count}[/]" if self.running else str(running_count)
        indicators: list[str] = []
        if self.category_filter:
            indicators.append(f"[magenta]cat: {self.category_filter}[/]")
        if self.scope_policy is not None and self.scope_policy.enabled:
            indicators.append("[red]scope: on[/]")
        if self.history_store.enabled:
            indicators.append("[blue]history: on[/]")
        extras = f"  {'  '.join(indicators)}" if indicators else ""
        left.update(
            f"Ambrosia v2  [session: {session_status}]  [commands: {len(self.commands)}]  "
            f"[running: {running_text}]{extras}"
        )
        right.update("[q]uit")

    def _refresh_mode_indicator(self) -> None:
        indicator = self.query_one("#search-mode-indicator", Static)
        indicator.update(f"search mode: {self.search_mode}  ([b]r[/b]/[b]f[/b] to cycle)")

    def _refresh_footer(self) -> None:
        footer = self.query_one("#footer", Static)
        footer.update(
            "[b]/[/b] search   [b]Tab[/b] next   [b]Enter[/b] run   [b]Esc[/b] back   "
            "[b]r/f[/b] mode   [b]q[/b] quit   [b]?[/b] help\n"
            "[b]n[/b] add   [b]e[/b] edit   [b]d[/b] delete   [b]*[/b] ★ favorite   "
            "[b]p[/b] pin   [b]F[/b] favorites   [b]h[/b] history   [b]S[/b] scope"
        )

    # ------------------------------------------------------------------ session persistence

    def _on_session_changed(self) -> None:
        """Invoked by SessionState whenever remembered values change."""
        self._session_dirty = True
        self._refresh_top_bar()
        self._schedule_auto_save()

    def _schedule_auto_save(self) -> None:
        """Debounce session persistence: save 150 ms after the last change."""
        if self._auto_save_task is not None:
            self._auto_save_task.cancel()
        self._auto_save_task = asyncio.create_task(self._auto_save_session())

    async def _auto_save_session(self) -> None:
        """Persist the session after the debounce window if it is still dirty."""
        try:
            await asyncio.sleep(0.15)
        except asyncio.CancelledError:
            return
        if not self._session_dirty:
            return
        self.session_store.save(self.session, exclude_secrets=True)
        self._session_dirty = False
        self._refresh_top_bar()

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
            await asyncio.sleep(self.SEARCH_DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            return
        search = self.query_one("#search-bar", SearchBar)
        self.search_query = search.value

    def on_execution_view_command_finished(self, event: ExecutionView.CommandFinished) -> None:
        """Record the last finished result so it can be re-run.

        Status styling (green for exit 0, red for non-zero, yellow for
        cancelled) is applied by :meth:`ExecutionView.finish` when it posts
        this message.
        """
        exit_code = 0 if event.exit_code is None else event.exit_code
        self._last_result = CommandResult(
            exit_code=exit_code,
            duration_ms=event.duration_ms,
            stdout="",
            stderr="",
            cancelled=event.cancelled,
        )

    # ------------------------------------------------------------------ actions

    def action_focus_search(self) -> None:
        self.query_one("#search-bar", SearchBar).focus_input()

    def action_focus_results(self) -> None:
        self.query_one("#results", ResultsList).focus()

    def action_focus_next(self) -> None:
        """Cycle focus: search bar → results list → execution view (if visible) → search."""
        search = self.query_one("#search-bar", SearchBar)
        results = self.query_one("#results", ResultsList)
        execution = self.query_one("#execution-view", ExecutionView)

        if search.has_focus:
            results.focus()
        elif results.has_focus:
            if self.execution_visible:
                execution.focus_log()
            else:
                search.focus_input()
        else:
            # Execution view (or anything else) has focus → back to search.
            search.focus_input()

    def action_toggle_regex(self) -> None:
        """Cycle the search mode (substring → fuzzy → regex → substring).

        Kept for compatibility with :class:`~ambrosia.tui.widgets.search.SearchBar`,
        which binds ``r`` directly to this action. Both ``r`` and ``f`` now
        cycle the same way; there is no longer a separate regex on/off toggle.
        """
        self.action_cycle_search_mode()

    def action_cycle_search_mode(self) -> None:
        """Cycle search modes: substring → fuzzy → regex → substring."""
        if self.execution_visible:
            return
        modes: tuple[SearchMode, ...] = ("substring", "fuzzy", "regex")
        index = modes.index(self.search_mode)
        self.search_mode = modes[(index + 1) % len(modes)]

    def action_toggle_favorite_on_selected(self) -> None:
        """Toggle the favorite flag on the selected command and persist the catalog."""
        if self.execution_visible:
            return
        results = self.query_one("#results", ResultsList)
        command = results.selected_command()
        if command is None:
            return
        updated = Command(
            id=command.id,
            name=command.name,
            description=command.description,
            tags=list(command.tags),
            shell=command.shell,
            inputs=list(command.inputs),
            category=command.category,
            favorite=not command.favorite,
            pinned=command.pinned,
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
        self.notify(f"command {'favorited' if updated.favorite else 'unfavorited'}")

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
        hints = {
            input_.id: input_.validation_hint for input_ in command.inputs if input_.validation_hint
        }
        modal = InputFormModal(
            f"Inputs for {command.name}",
            fields,
            initial=initial,
            submit_label="Run",
            hints=hints,
        )
        self.push_screen(modal, lambda values: self._handle_input_form(values, command))

    def _handle_input_form(self, values: dict[str, str] | None, command: Command) -> None:
        if values is None:
            return
        self.session.set_all(command.id, values)
        asyncio.create_task(self._run_command(command, values))

    def _extract_scope_target(self, command: Command, values: dict[str, str]) -> str | None:
        """Return the execution target for scope checking.

        Prefers the value of a ``host``-typed input; otherwise returns the first
        value that parses as an IPv4/IPv6 address. Returns ``None`` when there is
        no IP target to validate (e.g. a hostname-only command), in which case
        the scope check is skipped.
        """
        for input_ in command.inputs:
            if input_.type == "host":
                value = values.get(input_.id, "").strip()
                if value:
                    return value
        for value in values.values():
            try:
                ipaddress.ip_address(value.strip())
            except ValueError:
                continue
            return value.strip()
        return None

    async def _run_command(self, command: Command, values: dict[str, str]) -> None:
        # Scope check: block execution when the target IP is outside the policy.
        if self.scope_policy is not None and self.scope_policy.enabled:
            target = self._extract_scope_target(command, values)
            if target is not None:
                check_result = check_target(target, self.scope_policy)
                if not check_result.allowed:
                    self.notify(f"scope blocked: {check_result.reason}")
                    return
        # Remember this command as recently used.
        self.session.add_recent(command.id, command.name)
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
                # Keep the execution view visible so the cancelled status
                # (set by action_cancel_job) remains on screen; the operator
                # can then run again or go back.
                return
            self.running = False
            execution.finish(result.exit_code, result.duration_ms, cancelled=result.cancelled)
            # Log to history (opt-in; a disabled store is a no-op).
            if self.history_store.enabled:
                self.history_store.add(
                    make_entry(
                        command.id,
                        command.name,
                        argv,
                        result.exit_code,
                        result.duration_ms,
                        cancelled=result.cancelled,
                    )
                )

        self._run_task = asyncio.create_task(_run())

    async def _on_output(self, text: str) -> None:
        self.query_one("#execution-view", ExecutionView).write_line(text)

    def action_cancel_job(self) -> None:
        if not self.running:
            return
        self.executor.cancel()
        execution = self.query_one("#execution-view", ExecutionView)
        execution.finish(None, 0, cancelled=True)
        if self._run_task is not None:
            self._run_task.cancel()

    def action_run_again(self) -> None:
        """Re-run the last command with the same saved values, if any."""
        if self._last_command is None or not self._last_values:
            return
        asyncio.create_task(self._run_command(self._last_command, self._last_values))

    def action_cycle_category_filter(self) -> None:
        """Cycle the category filter through "All" and each available category."""
        if self.execution_visible:
            return
        categories: list[str] = [""] + get_categories(self.commands)
        current = self.category_filter
        index = categories.index(current) if current in categories else -1
        self.category_filter = categories[(index + 1) % len(categories)]

    def action_toggle_favorites(self) -> None:
        """Toggle showing only favorite commands."""
        if self.execution_visible:
            return
        self.show_favorites_only = not self.show_favorites_only

    def action_toggle_pinned(self) -> None:
        """Toggle the pinned flag on the selected command and persist the catalog."""
        if self.execution_visible:
            return
        results = self.query_one("#results", ResultsList)
        command = results.selected_command()
        if command is None:
            return
        updated = Command(
            id=command.id,
            name=command.name,
            description=command.description,
            tags=list(command.tags),
            shell=command.shell,
            inputs=list(command.inputs),
            category=command.category,
            favorite=command.favorite,
            pinned=not command.pinned,
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
        self.notify(f"command {'pinned' if updated.pinned else 'unpinned'}")

    def action_toggle_history(self) -> None:
        """Toggle execution history logging on or off (opt-in)."""
        self.history_store.enabled = not self.history_store.enabled
        state = "on" if self.history_store.enabled else "off"
        self.notify(f"history logging {state}")

    def action_toggle_scope(self) -> None:
        """Toggle the IP scope policy on or off and persist it."""
        if self.scope_policy is None:
            self.scope_policy = load_scope_policy()
        self.scope_policy = replace(self.scope_policy, enabled=not self.scope_policy.enabled)
        save_scope_policy(self.scope_policy)
        state = "on" if self.scope_policy.enabled else "off"
        self.notify(f"scope {state}")

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
            category=command.category,
            favorite=command.favorite,
            pinned=command.pinned,
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

    def action_export_commands(self) -> None:
        if self.execution_visible:
            return
        default_path = Path.home() / ".ambrosia" / "commands-export.json"
        modal = InputFormModal(
            "Export commands",
            [("path", "Export to path", True, False)],
            initial={"path": str(default_path)},
            submit_label="Export",
        )
        self.push_screen(modal, self._handle_export_path)

    def _handle_export_path(self, values: dict[str, str] | None) -> None:
        if not values:
            return
        raw_path = values.get("path", "").strip()
        if not raw_path:
            self.notify("a path is required")
            return
        try:
            export_commands(list(self.commands), Path(raw_path))
        except Exception as exc:  # noqa: BLE001 - surface storage failure
            self.notify(f"export failed: {exc}")
            return
        self.notify(f"exported {len(self.commands)} commands to {raw_path}")

    def action_import_commands(self) -> None:
        if self.execution_visible:
            return
        modal = InputFormModal(
            "Import commands",
            [("path", "Import from path", True, False)],
            submit_label="Import",
        )
        self.push_screen(modal, self._handle_import_path)

    def _handle_import_path(self, values: dict[str, str] | None) -> None:
        if not values:
            return
        raw_path = values.get("path", "").strip()
        if not raw_path:
            self.notify("a path is required")
            return
        try:
            merged = import_commands(Path(raw_path), merge=True)
        except Exception as exc:  # noqa: BLE001 - surface storage failure
            self.notify(f"import failed: {exc}")
            return
        self.commands = list(merged)
        save_commands(self.commands)
        self._recompute_filtered()
        self.notify(f"imported {len(merged)} commands")

    def action_save_session(self) -> None:
        self.session_store.save(self.session, exclude_secrets=True)
        self._session_dirty = False
        self._refresh_top_bar()
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
        if self._auto_save_task is not None:
            self._auto_save_task.cancel()
            self._auto_save_task = None
        self.session_store.save(self.session, exclude_secrets=True)
        self._session_dirty = False
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
    """Keyboard reference, grouped by category."""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Ambrosia v2 — keyboard reference", id="title")
            yield Static(
                "[b]Navigation[/]\n"
                "  [b]/[/b]   focus search bar\n"
                "  [b]Tab[/b]     move focus between regions\n"
                "  [b]Enter[/b]   select highlighted command / run\n"
                "  [b]Esc[/b]     clear search / close modal / back\n"
                "  [b]b[/b]       back from the execution view\n"
                "\n"
                "[b]Search[/]\n"
                "  [b]r[/b]   cycle search mode (substring → fuzzy → regex)\n"
                "  [b]f[/b]   cycle search mode (same as ``r``)\n"
                "  [b]][/b]   cycle category filter (All → category → All)\n"
                "  [b]F[/b]   toggle favorites-only filter\n"
                "\n"
                "[b]Execution[/]\n"
                "  [b]c[/b]   cancel the running job\n"
                "  [b]g[/b]   run the last command again\n"
                "  [b]s[/b]   save session inputs\n"
                "\n"
                "[b]Commands[/]\n"
                "  [b]n[/b]   add a new command\n"
                "  [b]e[/b]   edit the selected command\n"
                "  [b]d[/b]   delete the selected command (confirm)\n"
                "  [b]i[/b]   import commands from a JSON file (merge by id)\n"
                "  [b]E[/b]   export commands to a JSON file\n"
                "  [b]p[/b]   toggle pinned on the selected command\n"
                "  [b]*[/b]   toggle favorite on the selected command\n"
                "  [b]h[/b]   toggle history logging on/off\n"
                "  [b]S[/b]   toggle scope policy on/off\n"
                "\n"
                "[b]Controls[/]\n"
                "  [b]q[/b]   quit (confirm if a job is running)\n"
                "  [b]?[/b]   show this help\n",
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
