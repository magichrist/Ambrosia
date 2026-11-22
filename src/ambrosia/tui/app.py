"""Ambrosia v2 TUI: a three-panel preset workstation.

Layout:

* top bar          - session status, preset count, running state, scope/history
* sidebar          - library views and tag filters
* explorer         - live search and ranked preset results
* inspector        - full detail and run/edit controls for the selected preset
* execution view   - replaces the workstation while a job runs

The app depends only on the :mod:`ambrosia` adapters and never on the v1 TUI.
"""

from __future__ import annotations

import asyncio
import ipaddress
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
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
from ambrosia.model import Command, CommandInput, inputs_from_shell
from ambrosia.scope import ScopePolicy, check_target, load_scope_policy, save_scope_policy
from ambrosia.session import SessionState, SessionStore
from ambrosia.storage import (
    add_command,
    export_commands,
    get_all_tags,
    import_commands,
    load_commands,
    remove_command,
    save_commands,
)
from ambrosia.tui.design import (
    AMBER,
    DARK_PANEL_BG,
    DEEP_PANEL_BG,
    FEMME_PINK,
    GUMMY_AMBER,
    GUMMY_LIGHT_PINK,
    GUMMY_PINK,
    GUMMY_RED,
    HOVER_BG,
    PHOSPHOR,
    SELECTED_BG,
    TEXT_MUTED,
    TEXT_PRIMARY,
    YELLOW,
)
from ambrosia.tui.matching import (
    SearchMode,
    regex_error,
    search_commands,
    search_items,
    search_workflows,
)
from ambrosia.tui.widgets.execution_view import ExecutionView
from ambrosia.tui.widgets.input_form import InputFormModal
from ambrosia.tui.widgets.preview import PresetInspector
from ambrosia.tui.widgets.results import PresetExplorer
from ambrosia.tui.widgets.search import SearchBar, parse_search_query
from ambrosia.tui.widgets.tags import TagBrowser
from ambrosia.tui.widgets.workflow_view import WorkflowView
from ambrosia.workflow import Workflow, load_workflows_from_dir

if TYPE_CHECKING:
    from textual.events import Key, Resize

    from ambrosia.tui.matching import SearchResult

SESSION_FILE = Path.home() / ".ambrosia" / "session.json"

LIBRARY_ALL = "all"
LIBRARY_FAVORITES = "favorites"
LIBRARY_PINNED = "pinned"
LIBRARY_RECENT = "recent"

_INPUT_FLAG_TYPES = ("host", "path", "integer", "string")


def _parse_input_spec(spec: str) -> dict[str, CommandInput]:
    """Parse ``id:prompt:flags`` entries into input overrides.

    Entries are comma-separated. ``flags`` is ``+``-separated and may contain
    ``optional``, ``secret``, and a type hint (``host``, ``path``, ``integer``).
    Anything else falls back to a required, non-secret string input.
    """
    overrides: dict[str, CommandInput] = {}
    for raw_entry in spec.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        parts = [part.strip() for part in entry.split(":")]
        input_id = parts[0]
        if not input_id:
            continue
        prompt = parts[1] if len(parts) > 1 and parts[1] else input_id
        flags = {
            flag.strip().lower()
            for flag in (parts[2] if len(parts) > 2 else "").split("+")
            if flag.strip()
        }
        input_type = next((kind for kind in _INPUT_FLAG_TYPES if kind in flags), "string")
        overrides[input_id] = CommandInput(
            id=input_id,
            prompt=prompt,
            type=input_type,
            required="optional" not in flags,
            secret="secret" in flags,
        )
    return overrides


def _format_input_spec(inputs: list[CommandInput]) -> str:
    """Render inputs back into the compact ``id:prompt:flags`` form."""
    entries: list[str] = []
    for input_ in inputs:
        flags: list[str] = []
        if not input_.required:
            flags.append("optional")
        if input_.secret:
            flags.append("secret")
        if input_.type != "string":
            flags.append(input_.type)
        prompt = input_.prompt if input_.prompt != input_.id else ""
        entry = input_.id
        if prompt or flags:
            entry += f":{prompt}"
        if flags:
            entry += f":{'+'.join(flags)}"
        entries.append(entry)
    return ", ".join(entries)


def _build_inputs(
    shell: str, spec: str, existing: list[CommandInput] | None = None
) -> list[CommandInput]:
    """Derive inputs from ``{{...}}`` placeholders, applying optional overrides.

    The shell template is the source of truth: only placeholders in ``shell``
    become inputs. An existing definition for a placeholder is preserved unless
    the operator supplies an explicit override in ``spec``.
    """
    previous = {input_.id: input_ for input_ in (existing or [])}
    overrides = _parse_input_spec(spec)
    result: list[CommandInput] = []
    for base in inputs_from_shell(shell):
        if base.id in overrides:
            result.append(overrides[base.id])
        elif base.id in previous:
            result.append(previous[base.id])
        else:
            result.append(base)
    return result

# Shared styling for small, centered popup dialogs.
MODAL_CSS = f"""
Screen {{
    align: center middle;
}}
.dialog {{
    width: 68;
    height: auto;
    max-height: 85%;
    background: {DARK_PANEL_BG};
    border: round {GUMMY_PINK};
    padding: 1 2;
}}
.dialog #confirm-message,
.dialog #title {{
    width: 100%;
    text-align: center;
    color: {PHOSPHOR};
    text-style: bold;
    margin-bottom: 1;
}}
.dialog-actions {{
    height: auto;
    width: 100%;
    content-align: right middle;
    margin-top: 1;
}}
.dialog-actions Button {{
    width: auto;
    margin-left: 1;
}}
.dialog-actions .spacer {{
    width: 1fr;
}}
.dialog #help-text {{
    height: auto;
    width: 100%;
}}
"""


class AmbrosiaApp(App[None]):
    """The v2 Textual application."""

    # Debounce delay for live search filtering (seconds).
    SEARCH_DEBOUNCE_SECONDS: float = 0.075

    # Focus the search bar on mount, not the first ListView (Textual's default).
    AUTO_FOCUS = "#search-bar"

    CSS = f"""
    Screen {{
        layout: vertical;
        background: {DEEP_PANEL_BG};
    }}
    #top-bar {{
        dock: top;
        height: 1;
        layout: horizontal;
        background: {DEEP_PANEL_BG};
        padding: 0 1;
    }}
    #top-bar-left {{
        width: 1fr;
        color: {PHOSPHOR};
    }}
    #top-bar-right {{
        width: auto;
        content-align: right middle;
        color: {AMBER};
    }}
    #main-split {{
        height: 1fr;
        layout: horizontal;
    }}
    #library {{
        width: 26;
        background: {DARK_PANEL_BG};
        border-right: solid {GUMMY_PINK};
        padding: 0 1;
        layout: vertical;
    }}
    #library Button.library-button {{
        width: 100%;
        margin: 0 0 1 0;
        background: {DARK_PANEL_BG};
        color: {GUMMY_LIGHT_PINK};
        border: solid {GUMMY_PINK};
    }}
    #library Button.library-button:hover {{
        background: {FEMME_PINK};
        color: {DEEP_PANEL_BG};
        text-style: bold;
    }}
    #library Button.library-button.--active {{
        background: {SELECTED_BG};
        color: {YELLOW};
        border: solid {AMBER};
    }}
    #library Button.library-button.--active:hover {{
        background: {AMBER};
        color: {DEEP_PANEL_BG};
    }}
    #explorer {{
        width: 1fr;
        layout: vertical;
        background: {DEEP_PANEL_BG};
    }}
    #search-bar {{
        height: 3;
        padding: 0 1;
        background: {DARK_PANEL_BG};
        border-bottom: solid {GUMMY_PINK};
    }}
    #search-mode-indicator {{
        height: 1;
        padding: 0 1;
        color: {AMBER};
        text-style: italic;
    }}
    #search-status {{
        height: 1;
        padding: 0 1;
        color: {GUMMY_RED};
    }}
    #preset-explorer {{
        height: 1fr;
        padding: 0 1;
        background: {DEEP_PANEL_BG};
    }}
    #preset-explorer ListItem {{
        height: auto;
        padding: 0 1;
    }}
    #preset-explorer ListItem > Static {{
        height: auto;
        width: 100%;
    }}
    #preset-explorer ListItem.-highlight {{
        background: {SELECTED_BG};
        color: {YELLOW};
    }}
    #preset-explorer ListItem.-hovered {{
        background: {HOVER_BG};
        color: {YELLOW};
    }}
    #preset-explorer ListItem.-highlight.-hovered {{
        background: {HOVER_BG};
        color: {YELLOW};
        text-style: bold;
    }}
    #preset-explorer ListItem.-hovered > Static {{
        background: transparent;
        color: {YELLOW};
    }}
    #search-bar:focus {{
        border: tall {AMBER};
    }}
    Checkbox:hover,
    RadioButton:hover {{
        background: {HOVER_BG};
        color: {YELLOW};
    }}
    Button:hover {{
        background: {AMBER};
        color: {DEEP_PANEL_BG};
        text-style: bold;
    }}
    Tooltip {{
        background: {DARK_PANEL_BG};
        color: {AMBER};
        border: round {FEMME_PINK};
        padding: 0 1;
    }}
    #library TagBrowser {{
        height: 1fr;
    }}
    #preset-inspector {{
        width: 54;
        background: {DARK_PANEL_BG};
        border-left: solid {GUMMY_PINK};
        padding: 0 1;
        layout: vertical;
    }}
    #workflow-view {{
        display: none;
    }}
    #workflow-view.visible {{
        display: block;
        height: 1fr;
        border-top: solid {GUMMY_PINK};
        layout: vertical;
    }}
    #execution-view {{
        display: none;
    }}
    #execution-view.visible {{
        display: block;
        height: 1fr;
        border-top: solid {GUMMY_PINK};
    }}
    #execution-view.hidden {{
        display: none;
    }}
    #execution-header {{
        height: 1;
        padding: 0 1;
        color: {PHOSPHOR};
        background: {SELECTED_BG};
    }}
    #execution-command {{
        height: 1;
        padding: 0 1;
        color: {GUMMY_LIGHT_PINK};
    }}
    #execution-status {{
        height: 1;
        padding: 0 1;
        color: {GUMMY_LIGHT_PINK};
    }}
    #execution-log {{
        height: 1fr;
        padding: 0 1;
    }}
    #execution-rule-header,
    #execution-rule-command,
    #execution-rule-log {{
        color: {GUMMY_PINK};
    }}
    #main-split.hidden,
    #top-bar.hidden {{
        display: none;
    }}
    #footer {{
        dock: bottom;
        height: 1;
        padding: 0 1;
        overflow: hidden;
        color: {GUMMY_LIGHT_PINK};
        background: {DARK_PANEL_BG};
    }}
    .hint {{
        color: {GUMMY_LIGHT_PINK};
        text-style: italic;
        margin: 0 0 1 0;
    }}
    """

    BINDINGS = [
        Binding("/", "focus_search", "Search", show=True),
        Binding("tab", "focus_next", "Next region", show=True),
        Binding("enter", "select", "Select / run", show=True),
        Binding("escape", "go_back", "Clear / back", show=True),
        Binding("ctrl+r", "cycle_search_mode", "Mode", show=False),
        Binding("r", "cycle_search_mode", "Mode", show=True),
        Binding("c", "copy_or_cancel", "Copy / cancel", show=True),
        Binding("x", "quick_run", "Quick run", show=True),
        Binding("g", "run_again", "Run again", show=True),
        Binding("s", "save_session", "Save session", show=True),
        Binding("b", "go_back", "Back", show=True),
        Binding("left", "go_back", "Back", show=True),
        Binding("n", "add_preset", "Add preset", show=False),
        Binding("e", "edit_preset", "Edit preset", show=False),
        Binding("d", "delete_preset", "Delete preset", show=False),
        Binding("i", "import_presets", "Import", show=False),
        Binding("E", "export_presets", "Export", show=False),
        Binding("f", "toggle_favorite_on_selected", "Favorite", show=False),
        Binding("p", "toggle_pinned", "Pin", show=False),
        Binding("h", "toggle_history", "History", show=False),
        Binding("S", "toggle_scope", "Scope", show=False),
        Binding("ctrl+q", "quit_app", "Quit", show=True),
        Binding("question_mark", "help", "Help", show=True),
    ]

    # ------------------------------------------------------------------ state

    search_query: reactive[str] = reactive("")
    search_mode: reactive[SearchMode] = reactive("substring")
    regex_error: reactive[str | None] = reactive(None)
    library_view: reactive[str] = reactive(LIBRARY_ALL)
    active_tags: reactive[list[str]] = reactive(list)
    tag_mode: reactive[str] = reactive("or")
    selected_item: reactive[Command | Workflow | None] = reactive(None)
    filtered_results: reactive[list[SearchResult]] = reactive(list)
    execution_visible: reactive[bool] = reactive(False)
    workflow_visible: reactive[bool] = reactive(False)
    running: reactive[bool] = reactive(False)

    def __init__(
        self,
        commands: list[Command] | None = None,
        workflows: list[Workflow] | None = None,
    ) -> None:
        super().__init__()
        self._startup_commands = commands
        self._startup_workflows = workflows
        self.commands: list[Command] = []
        self.workflows: list[Workflow] = []
        self.session = SessionState()
        self.session_store = SessionStore(SESSION_FILE)
        # Inputs remembered by input name for the lifetime of this process.
        self._session_values: dict[str, str] = {}
        self.scope_policy: ScopePolicy | None = None
        self.executor = ShellExecutor()
        self.history_store = HistoryStore()
        self.parsed_query = parse_search_query("", "substring")
        self._search_debounce_task: asyncio.Task[None] | None = None
        self._filter_task: asyncio.Task[None] | None = None
        self._auto_save_task: asyncio.Task[None] | None = None
        self._run_task: asyncio.Task[None] | None = None
        self._session_dirty = False
        self._last_command: Command | None = None
        self._last_values: dict[str, str] = {}
        self._execution_was_visible = False
        self.active_workflow: Workflow | None = None
        self.workflow_phase_index = 0
        self.workflow_command_index = 0
        self._quick_run_active = False
        self._quick_last_line = ""

    @property
    def selected_command(self) -> Command | None:
        """The highlighted preset, or ``None`` when a workflow is selected."""
        item = self.selected_item
        return item if isinstance(item, Command) else None

    @property
    def selected_workflow(self) -> Workflow | None:
        """The highlighted workflow, or ``None`` when a preset is selected."""
        item = self.selected_item
        return item if isinstance(item, Workflow) else None

    def get_css_variables(self) -> dict[str, str]:
        """Use the Female Cyber Space palette for Textual's theme variables."""
        variables = super().get_css_variables()
        warm = {
            "primary": AMBER,
            "primary-lighten-1": YELLOW,
            "primary-lighten-2": "#ffeba8",
            "primary-lighten-3": "#fff2c4",
            "primary-darken-1": "#d98f34",
            "primary-darken-2": "#b06f1d",
            "primary-darken-3": "#875211",
            "primary-muted": "#5a421c",
            "secondary": FEMME_PINK,
            "secondary-lighten-1": "#ff79b5",
            "secondary-lighten-2": "#ff96c6",
            "secondary-darken-1": "#d63f7b",
            "secondary-darken-2": "#ad2b62",
            "secondary-muted": "#5a2438",
            "accent": PHOSPHOR,
            "accent-lighten-1": "#c8ff87",
            "accent-darken-1": "#96d94a",
            "warning": YELLOW,
            "error": GUMMY_RED,
            "success": PHOSPHOR,
            "background": DEEP_PANEL_BG,
            "surface": DARK_PANEL_BG,
            "panel": DARK_PANEL_BG,
            # Focus/highlight colors that ship blue by default.
            "border": AMBER,
            "border-blurred": "#4a3a20",
            "block-cursor-background": SELECTED_BG,
            "block-cursor-foreground": YELLOW,
            "block-cursor-text-style": "bold",
            "block-cursor-blurred-background": "#3a2a0f99",
            "block-cursor-blurred-foreground": YELLOW,
            "block-hover-background": "#ffffff14",
            "scrollbar": "#6b4a17",
            "scrollbar-active": AMBER,
            "scrollbar-hover": "#8a5f1c",
            "scrollbar-background-hover": "#00000000",
            "link-background-hover": AMBER,
            "input-cursor-background": YELLOW,
            "input-cursor-foreground": DEEP_PANEL_BG,
            "text-accent": YELLOW,
            "text-primary": TEXT_PRIMARY,
            "text-secondary": TEXT_MUTED,
        }
        variables.update(warm)
        return variables

    # ------------------------------------------------------------------ compose / mount

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(id="top-bar-left"),
            Static(id="top-bar-right"),
            id="top-bar",
        )
        yield Horizontal(
            Vertical(
                Static("LIBRARY", classes="hint"),
                Button("ALL", id="lib-all", classes="library-button"),
                Button("FAVORITES", id="lib-favorites", classes="library-button"),
                Button("PINNED", id="lib-pinned", classes="library-button"),
                Button("RECENT", id="lib-recent", classes="library-button"),
                TagBrowser(id="tag-browser"),
                id="library",
            ),
            Vertical(
                SearchBar(id="search-bar"),
                Static(id="search-mode-indicator"),
                Static(id="search-status"),
                PresetExplorer(id="preset-explorer"),
                id="explorer",
            ),
            PresetInspector(id="preset-inspector"),
            id="main-split",
        )
        yield WorkflowView(id="workflow-view")
        yield ExecutionView(id="execution-view")
        yield Static(id="footer")

    def on_mount(self) -> None:
        # The session is memory-only: no file is loaded, and everything is
        # discarded when the operator quits.
        self.session = SessionState(on_change=self._on_session_changed)
        self._session_values = {}
        self._session_dirty = False
        self._auto_save_task = None
        self.commands = list(self._startup_commands) if self._startup_commands is not None else load_commands()
        if self._startup_workflows is not None:
            self.workflows = list(self._startup_workflows)
        else:
            default_dir = Path("inventory/workflow")
            self.workflows = (
                load_workflows_from_dir(default_dir) if default_dir.is_dir() else []
            )
        for command in self.commands:
            secret_ids = {input_.id for input_ in command.inputs if input_.secret}
            if secret_ids:
                self.session.register_secret_inputs(command.id, secret_ids)
        self.scope_policy = load_scope_policy()
        self.history_store = HistoryStore()
        self._rebuild()
        self._refresh_library_sidebar()
        self._refresh_top_bar()
        self._refresh_mode_indicator()
        self._refresh_footer()
        self._update_library_button_states()
        # The explorer's ListView would otherwise grab focus after mounting.
        self.set_timer(0, self.action_focus_search)

    # ------------------------------------------------------------------ watchers

    def watch_search_query(self, _query: str) -> None:
        self._rebuild()
        self._refresh_top_bar()

    def watch_search_mode(self, _mode: SearchMode) -> None:
        self._rebuild()
        self.query_one("#search-bar", SearchBar).set_search_mode(self.search_mode)
        self._refresh_mode_indicator()
        if self.search_mode != "regex":
            self.regex_error = None

    def watch_library_view(self, _view: str) -> None:
        self._rebuild()
        self._refresh_top_bar()
        self._update_library_button_states()

    def watch_active_tags(self, _tags: list[str]) -> None:
        self._rebuild()
        self._refresh_top_bar()

    def watch_tag_mode(self, _mode: str) -> None:
        self._rebuild()

    def watch_regex_error(self, error: str | None) -> None:
        self.query_one("#search-status", Static).update(error or "")

    def watch_filtered_results(self, results: list[SearchResult]) -> None:
        if self.selected_item is not None:
            items = {id(result.item) for result in results}
            if id(self.selected_item) not in items:
                self.selected_item = None
        explorer = self.query_one("#preset-explorer", PresetExplorer)
        if self._filter_task is not None:
            self._filter_task.cancel()
        self._filter_task = asyncio.create_task(explorer.set_results(results))

    def watch_selected_item(self, item: Command | Workflow | None) -> None:
        inspector = self.query_one("#preset-inspector", PresetInspector)
        if isinstance(item, Workflow):
            inspector.set_workflow(item)
        else:
            values = self._values_for(item) if item is not None else {}
            inspector.set_command(item, values)

    def watch_running(self, _running: bool) -> None:
        self._refresh_top_bar()

    def watch_execution_visible(self, visible: bool) -> None:
        was_visible = self._execution_was_visible
        self._execution_was_visible = visible
        self._apply_view_visibility(focus_explorer=was_visible and not visible)

    def watch_workflow_visible(self, visible: bool) -> None:
        if not visible:
            self.active_workflow = None
        self._apply_view_visibility()

    def _apply_view_visibility(self, *, focus_explorer: bool = False) -> None:
        """Show exactly one of: workflow runner, execution view, workstation."""
        top_bar = self.query_one("#top-bar", Horizontal)
        main_split = self.query_one("#main-split", Horizontal)
        workflow = self.query_one("#workflow-view", WorkflowView)
        execution = self.query_one("#execution-view", ExecutionView)

        if self.execution_visible:
            top_bar.add_class("hidden")
            main_split.add_class("hidden")
            workflow.remove_class("visible")
            workflow.add_class("hidden")
            execution.remove_class("hidden")
            execution.add_class("visible")
            execution.focus_log()
            return

        execution.remove_class("visible")
        execution.add_class("hidden")
        if self.workflow_visible:
            top_bar.add_class("hidden")
            main_split.add_class("hidden")
            workflow.remove_class("hidden")
            workflow.add_class("visible")
            workflow.focus_list()
            return

        workflow.remove_class("visible")
        workflow.add_class("hidden")
        top_bar.remove_class("hidden")
        main_split.remove_class("hidden")
        if focus_explorer:
            self.call_after_refresh(self.action_focus_explorer)

    # ------------------------------------------------------------------ filtering

    def _rebuild(self) -> None:
        self.filtered_results = self._build_filtered()

    def _build_filtered(self) -> list[SearchResult]:
        parsed = parse_search_query(self.search_query, self.search_mode)
        self.parsed_query = parsed
        if self.search_mode == "regex":
            error = regex_error(parsed)
            if error is not None:
                self.regex_error = error
                return []
        self.regex_error = None

        wanted = parsed.qualifiers.get("type", "").strip().lower()
        if wanted == "workflow":
            # Library views and tags are preset-only concepts; an explicit
            # workflow search should not be filtered by them.
            return search_workflows(self.workflows, parsed)

        base = list(self.commands)
        if self.library_view == LIBRARY_FAVORITES:
            base = [command for command in base if command.favorite]
        elif self.library_view == LIBRARY_PINNED:
            base = [command for command in base if command.pinned]
        elif self.library_view == LIBRARY_RECENT:
            recent_ids = {entry["command_id"] for entry in self.session.get_recent(50)}
            base = [command for command in base if command.id in recent_ids]

        if self.active_tags:
            tag_set = set(self.active_tags)
            if self.tag_mode == "and":
                base = [command for command in base if tag_set.issubset(set(command.tags))]
            else:
                base = [command for command in base if tag_set.intersection(command.tags)]

        if wanted == "all":
            return search_items(base, self.workflows, parsed)
        return search_commands(base, parsed)

    def _refresh_library_sidebar(self) -> None:
        self.query_one("#tag-browser", TagBrowser).set_tags(
            get_all_tags(self.commands), active_tags=list(self.active_tags)
        )

    def _update_library_button_states(self) -> None:
        for view in (LIBRARY_ALL, LIBRARY_FAVORITES, LIBRARY_PINNED, LIBRARY_RECENT):
            self.query_one(f"#lib-{view}", Button).set_class(view == self.library_view, "--active")

    # ------------------------------------------------------------------ header / footer

    def _refresh_top_bar(self) -> None:
        try:
            left = self.query_one("#top-bar-left", Static)
            right = self.query_one("#top-bar-right", Static)
        except NoMatches:
            # The app may still be finishing a subprocess task during teardown.
            return
        status = "RUNNING" if self.running else "READY"
        indicators: list[str] = []
        wanted = self.parsed_query.qualifiers.get("type", "").strip().lower()
        if wanted in ("preset", "workflow", "all"):
            indicators.append(f"type: {wanted}")
        if self.active_tags:
            indicators.append(f"tag: {','.join(self.active_tags)}")
        if self.scope_policy is not None and self.scope_policy.enabled:
            indicators.append("scope: on")
        if self.history_store.enabled:
            indicators.append("history: on")
        extras = f"   {'   '.join(indicators)}" if indicators else ""
        left.update(
            Text()
            .append("AMBROSIA  ", style=f"bold {PHOSPHOR}")
            .append("/  PRESET WORKSTATION   ", style=YELLOW)
            .append(f"● {status}   ", style=f"bold {AMBER}")
            .append(f"PRESETS {len(self.commands)}   ", style=GUMMY_LIGHT_PINK)
            .append(f"WORKFLOWS {len(self.workflows)}   ", style=GUMMY_AMBER)
            .append(f"RESULTS {len(self.filtered_results)}{extras}", style=FEMME_PINK)
        )
        right.update(
            Text()
            .append("[?] help   ", style=GUMMY_LIGHT_PINK)
            .append("[ctrl+q] quit", style=AMBER)
        )

    def _refresh_mode_indicator(self) -> None:
        self.query_one("#search-mode-indicator", Static).update(
            f"search mode: {self.search_mode}  ([b]ctrl+r[/b] to cycle while typing)"
        )

    def _refresh_footer(self) -> None:
        # Compact key:label tokens on a single line. The full reference is in
        # the "?" help modal, so the footer only needs to stay scannable.
        items: list[tuple[str, str]] = [
            ("/", "search"),
            ("Tab", "focus"),
            ("Enter", "run"),
            ("Esc", "back"),
            ("^R", "mode"),
            ("x", "quick"),
            ("c", "copy"),
            ("g", "again"),
            ("n", "add"),
            ("e", "edit"),
            ("d", "del"),
            ("f", "fav"),
            ("p", "pin"),
            ("s", "save"),
            ("h", "hist"),
            ("S", "scope"),
            ("^Q", "quit"),
            ("?", "help"),
        ]
        text = Text()
        for key, label in items:
            # Trailing spaces belong to the styled span: Textual strips
            # leading whitespace from a new styled span.
            text.append(f"{key}:", style=f"bold {PHOSPHOR}")
            text.append(f"{label} ", style=YELLOW)
        text.truncate(max(20, self.size.width - 2), overflow="ellipsis")
        try:
            self.query_one("#footer", Static).update(text)
        except NoMatches:
            # An early resize can arrive before the main screen is composed.
            return

    def on_resize(self, event: Resize) -> None:
        """Re-fit the one-line key map when the terminal width changes."""
        self._refresh_footer()

    # ------------------------------------------------------------------ session values

    def _values_for(self, command: Command) -> dict[str, str]:
        """Resolve values for ``command`` from the shared in-memory session.

        Values are keyed by input id, so entering ``target`` once makes it
        available to every other preset that declares a ``target`` input.
        Per-preset values (if any) take precedence over shared ones.
        """
        input_ids = {input_.id for input_ in command.inputs}
        values = {key: value for key, value in self._session_values.items() if key in input_ids}
        values.update(
            {
                key: value
                for key, value in self.session.get_all(command.id).items()
                if key in input_ids
            }
        )
        return values

    def _remember_values(self, command: Command, values: dict[str, str]) -> None:
        """Store values both for this preset and for the shared session."""
        self.session.set_all(command.id, values)
        for key, value in values.items():
            if value:
                self._session_values[key] = value

    def _missing_required(self, command: Command, values: dict[str, str]) -> bool:
        return any(not values.get(input_.id) for input_ in command.required_inputs())

    # ------------------------------------------------------------------ session persistence

    def _on_session_changed(self) -> None:
        self._session_dirty = True
        self._refresh_top_bar()

    # ------------------------------------------------------------------ message handlers

    def on_input_changed(self, event: Input.Changed) -> None:
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
        self.search_query = self.query_one("#search-bar", SearchBar).value

    def on_preset_explorer_item_highlighted(self, event: PresetExplorer.ItemHighlighted) -> None:
        self.selected_item = event.item
        event.stop()

    def on_preset_explorer_item_activated(self, event: PresetExplorer.ItemActivated) -> None:
        if self.execution_visible:
            return
        self.selected_item = event.item
        if isinstance(event.item, Workflow):
            asyncio.create_task(self.action_open_workflow(event.item))
        else:
            self._resolve_and_run(event.item)
        event.stop()

    def on_workflow_view_command_chosen(self, event: WorkflowView.CommandChosen) -> None:
        command = next((c for c in self.commands if c.id == event.command_id), None)
        if command is None:
            self.notify(f"preset not found: {event.command_id}")
            return
        self._workflow_command_index = self.query_one(
            "#workflow-view", WorkflowView
        ).selected_index()
        self._resolve_and_run(command)
        event.stop()

    def on_tag_browser_tags_changed(self, event: TagBrowser.TagsChanged) -> None:
        self.active_tags = list(event.tags)
        self.tag_mode = event.mode
        event.stop()

    def on_preset_inspector_toggle_favorite(self, event: PresetInspector.ToggleFavorite) -> None:
        self.action_toggle_favorite_on_selected()
        event.stop()

    def on_preset_inspector_toggle_pinned(self, event: PresetInspector.TogglePinned) -> None:
        self.action_toggle_pinned()
        event.stop()

    def on_preset_inspector_run_requested(self, event: PresetInspector.RunRequested) -> None:
        if self.selected_command is not None and not self.execution_visible:
            self._resolve_and_run(self.selected_command)
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        views = {
            "lib-all": LIBRARY_ALL,
            "lib-favorites": LIBRARY_FAVORITES,
            "lib-pinned": LIBRARY_PINNED,
            "lib-recent": LIBRARY_RECENT,
        }
        if button_id in views:
            self.library_view = views[button_id]
        elif button_id == "run-again":
            self.action_run_again()
        event.stop()

    def on_execution_view_command_finished(self, event: ExecutionView.CommandFinished) -> None:
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

    def action_focus_explorer(self) -> None:
        self.query_one("#preset-explorer", PresetExplorer).focus()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Disable app-level bindings while a modal screen is on top."""
        if len(self.screen_stack) > 1:
            return False
        return True

    def action_focus_next(self) -> None:
        """Cycle focus: search → explorer → inspector run button → search."""
        search = self.query_one("#search-bar", SearchBar)
        explorer = self.query_one("#preset-explorer", PresetExplorer)
        inspector = self.query_one("#preset-inspector", PresetInspector)
        run_button = inspector.query_one("#configure-run", Button)
        if search.has_focus:
            explorer.focus()
        elif explorer.has_focus:
            if run_button.disabled:
                search.focus_input()
            else:
                run_button.focus()
        else:
            search.focus_input()

    def action_cycle_search_mode(self) -> None:
        if self.execution_visible:
            return
        modes: tuple[SearchMode, ...] = ("substring", "fuzzy", "regex")
        self.search_mode = modes[(modes.index(self.search_mode) + 1) % len(modes)]

    async def action_select(self) -> None:
        search = self.query_one("#search-bar", SearchBar)
        if search.has_focus:
            self.action_focus_explorer()
            return
        if self.execution_visible:
            if self._last_command is not None:
                await self._run_command(self._last_command, self._last_values)
            return
        command = self.selected_command
        if command is None:
            return
        self._resolve_and_run(command)

    def action_toggle_favorite_on_selected(self) -> None:
        command = self.selected_command
        if command is None:
            return
        updated = replace(command, favorite=not command.favorite)
        self.commands = [updated if c.id == command.id else c for c in self.commands]
        try:
            save_commands(self.commands)
        except Exception as exc:  # noqa: BLE001 - surface storage failure
            self.notify(f"save failed: {exc}")
            return
        self._rebuild()
        self._refresh_library_sidebar()
        self.notify(f"preset {'favorited' if updated.favorite else 'unfavorited'}")

    def action_toggle_pinned(self) -> None:
        command = self.selected_command
        if command is None:
            return
        updated = replace(command, pinned=not command.pinned)
        self.commands = [updated if c.id == command.id else c for c in self.commands]
        try:
            save_commands(self.commands)
        except Exception as exc:  # noqa: BLE001 - surface storage failure
            self.notify(f"save failed: {exc}")
            return
        self._rebuild()
        self.notify(f"preset {'pinned' if updated.pinned else 'unpinned'}")

    # ------------------------------------------------------------------ run flow

    def _resolve_and_run(self, command: Command) -> None:
        values = self._values_for(command)
        if self._missing_required(command, values):
            self._open_input_form(command)
        else:
            self._confirm_run(command, values)

    def _confirm_run(self, command: Command, values: dict[str, str] | None = None) -> None:
        resolved = values if values is not None else self._values_for(command)
        argv = build_argv(command.shell, resolved)
        modal = _ConfirmRunModal(command, argv)
        self.push_screen(
            modal, lambda outcome: self._handle_confirm_run(outcome, command, resolved)
        )

    def _handle_confirm_run(
        self, outcome: str | None, command: Command, values: dict[str, str]
    ) -> None:
        if outcome == "run":
            asyncio.create_task(self._run_command(command, values))
        elif outcome == "edit":
            self._open_input_form(command)

    def _open_input_form(self, command: Command, *, quick: bool = False) -> None:
        fields = [
            (input_.id, input_.prompt, input_.required, input_.secret) for input_ in command.inputs
        ]
        modal = InputFormModal(
            f"Inputs for {command.name}",
            fields,
            initial=self._values_for(command),
            submit_label="Run",
            hints={
                input_.id: input_.validation_hint
                for input_ in command.inputs
                if input_.validation_hint
            },
        )
        self.push_screen(
            modal, lambda values: self._handle_input_form(values, command, quick=quick)
        )

    def _handle_input_form(
        self, values: dict[str, str] | None, command: Command, *, quick: bool = False
    ) -> None:
        if values is None:
            return
        self._remember_values(command, values)
        asyncio.create_task(self._run_command(command, values, quick=quick))

    @staticmethod
    def _extract_scope_target(command: Command, values: dict[str, str]) -> str | None:
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

    async def _run_command(
        self, command: Command, values: dict[str, str], *, quick: bool = False
    ) -> None:
        if self.scope_policy is not None and self.scope_policy.enabled:
            target = self._extract_scope_target(command, values)
            if target is not None:
                result = check_target(target, self.scope_policy)
                if not result.allowed:
                    self.notify(f"scope blocked: {result.reason}")
                    return
        self.session.add_recent(command.id, command.name)
        self._remember_values(command, values)
        argv = build_argv(command.shell, values)
        execution = self.query_one("#execution-view", ExecutionView)
        execution.start(command.name, argv)
        self.running = True
        self._last_command = command
        self._last_values = dict(values)
        inspector = self.query_one("#preset-inspector", PresetInspector)
        if quick:
            # Quick run keeps the workstation on screen and reports only a
            # one-line status in the inspector.
            self._quick_run_active = True
            self._quick_last_line = ""
            inspector.set_quick_status(f"running: {command.name}")
        else:
            self.execution_visible = True

        async def _run() -> None:
            try:
                result = await self.executor.run(command.shell, values, on_output=self._on_output)
            except ExecutableNotFoundError as exc:
                execution.write_line(str(exc))
                if quick:
                    self._quick_last_line = str(exc)
                result = CommandResult(
                    exit_code=127, duration_ms=0, stdout="", stderr="", cancelled=False
                )
            except asyncio.CancelledError:
                self.running = False
                if quick:
                    self._quick_run_active = False
                    inspector.set_quick_status("cancelled")
                return
            self.running = False
            execution.finish(result.exit_code, result.duration_ms, cancelled=result.cancelled)
            if quick:
                self._quick_run_active = False
                detail = f" · {self._quick_last_line[:40]}" if self._quick_last_line else ""
                inspector.set_quick_status(
                    f"exit {result.exit_code} · {result.duration_ms / 1000:.2f}s{detail}"
                )
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
        if self._quick_run_active and text.strip():
            self._quick_last_line = text.strip()
            self.query_one("#preset-inspector", PresetInspector).set_quick_status(
                f"running · {self._quick_last_line[:70]}"
            )

    def action_cancel_job(self) -> None:
        if not self.running:
            return
        self.executor.cancel()
        execution = self.query_one("#execution-view", ExecutionView)
        execution.finish(None, 0, cancelled=True)
        if self._run_task is not None:
            self._run_task.cancel()

    def action_quick_run(self) -> None:
        """Run the selected preset immediately, with a minimal result in the inspector."""
        if self.execution_visible:
            return
        command = self.selected_command
        if command is None:
            self.notify("no preset selected")
            return
        values = self._values_for(command)
        if self._missing_required(command, values):
            self._open_input_form(command, quick=True)
            return
        asyncio.create_task(self._run_command(command, values, quick=True))

    def action_copy_or_cancel(self) -> None:
        if self.execution_visible and self.running:
            self.action_cancel_job()
            return
        command = self.selected_command
        if command is None:
            self.notify("no preset selected")
            return
        compiled = " ".join(build_argv(command.shell, self._values_for(command)))
        if self._copy_to_clipboard(compiled):
            self.notify(f"copied: {compiled}")
        else:
            self.notify("clipboard copy failed")

    @staticmethod
    def _copy_to_clipboard(text: str) -> bool:
        for cmd in (["pbcopy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
            if shutil.which(cmd[0]) is None:
                continue
            try:
                subprocess.run(cmd, input=text, text=True, check=True, timeout=5)  # noqa: S603
                return True
            except (subprocess.SubprocessError, OSError, FileNotFoundError):
                continue
        return False

    def action_run_again(self) -> None:
        if self._last_command is None or not self._last_values:
            return
        asyncio.create_task(self._run_command(self._last_command, self._last_values))

    def action_go_back(self) -> None:
        if self.execution_visible:
            self.execution_visible = False
        elif self.workflow_visible:
            self.workflow_visible = False
        elif self.search_query:
            self.search_query = ""
        elif self.active_tags:
            self.active_tags = []
        elif self.library_view != LIBRARY_ALL:
            self.library_view = LIBRARY_ALL

    # ------------------------------------------------------------------ workflow runner

    async def _render_workflow_phase(self) -> None:
        workflow = self.active_workflow
        if workflow is None:
            return
        names = workflow.phase_names()
        if names:
            self.workflow_phase_index = max(0, min(self.workflow_phase_index, len(names) - 1))
        else:
            self.workflow_phase_index = 0
        await self.query_one("#workflow-view", WorkflowView).set_workflow(
            workflow,
            {command.id: command for command in self.commands},
            self.workflow_phase_index,
            self.workflow_command_index,
        )

    async def action_open_workflow(self, workflow: Workflow) -> None:
        """Open a workflow at phase 1 so the operator can pick a command."""
        if self.execution_visible:
            return
        self.active_workflow = workflow
        self.workflow_phase_index = 0
        self.workflow_command_index = 0
        self.workflow_visible = True
        await self._render_workflow_phase()

    async def _shift_workflow_phase(self, delta: int) -> None:
        if not self.workflow_visible or self.active_workflow is None:
            return
        view = self.query_one("#workflow-view", WorkflowView)
        self.workflow_command_index = view.selected_index()
        names = self.active_workflow.phase_names()
        target = self.workflow_phase_index + delta
        if not names or not 0 <= target < len(names):
            return
        self.workflow_phase_index = target
        self.workflow_command_index = 0
        await self._render_workflow_phase()

    async def action_workflow_next_phase(self) -> None:
        """Move to the next phase of the active workflow."""
        await self._shift_workflow_phase(1)

    async def action_workflow_prev_phase(self) -> None:
        """Move to the previous phase, or leave the runner from phase 1."""
        if not self.workflow_visible or self.active_workflow is None:
            return
        if self.workflow_phase_index == 0:
            # Left on the first phase behaves like Esc: return to the main TUI.
            self.action_go_back()
            return
        await self._shift_workflow_phase(-1)

    # ------------------------------------------------------------------ preset CRUD

    def action_add_preset(self) -> None:
        if self.execution_visible:
            return
        fields = [
            ("id", "Preset id", True, False),
            ("name", "Display name", True, False),
            ("shell", "Command template", True, False),
            ("inputs", "Input overrides", False, False),
            ("path", "Logical path (dot-delimited)", False, False),
            ("description", "Description", False, False),
            ("tags", "Tags (comma-separated)", False, False),
        ]
        hints = {
            "shell": "{{name}} placeholders become inputs automatically.",
            "inputs": "id:prompt:flags; flags: optional secret host path",
        }
        self.push_screen(
            InputFormModal("Add preset", fields, submit_label="Add", hints=hints),
            self._handle_add_preset,
        )

    def _handle_add_preset(self, values: dict[str, str] | None) -> None:
        if not values:
            return
        command_id = values.get("id", "").strip()
        name = values.get("name", "").strip()
        shell = values.get("shell", "").strip()
        if not command_id or not name or not shell:
            self.notify("id, name, and shell are required")
            return
        inputs = _build_inputs(shell, values.get("inputs", ""))
        command = Command(
            id=command_id,
            name=name,
            description=values.get("description", ""),
            tags=[tag.strip() for tag in values.get("tags", "").split(",") if tag.strip()],
            shell=shell,
            inputs=inputs,
            category=values.get("path", "").strip(),
        )
        try:
            add_command(command)
        except ValueError as exc:
            self.notify(str(exc))
            return
        self.commands = [*self.commands, command]
        self._rebuild()
        self._refresh_library_sidebar()
        detail = f" (inputs: {', '.join(i.id for i in inputs)})" if inputs else ""
        self.notify(f"preset added{detail}")

    def action_edit_preset(self) -> None:
        if self.execution_visible:
            return
        command = self.selected_command
        if command is None:
            return
        fields = [
            ("id", "Preset id", True, False),
            ("name", "Display name", True, False),
            ("shell", "Command template", True, False),
            ("inputs", "Input overrides", False, False),
            ("path", "Logical path (dot-delimited)", False, False),
            ("description", "Description", False, False),
            ("tags", "Tags (comma-separated)", False, False),
        ]
        hints = {
            "shell": "{{name}} placeholders become inputs automatically.",
            "inputs": "id:prompt:flags; flags: optional secret host path",
        }
        initial = {
            "id": command.id,
            "name": command.name,
            "path": command.category,
            "description": command.description,
            "tags": ", ".join(command.tags),
            "shell": command.shell,
            "inputs": _format_input_spec(command.inputs),
        }
        self.push_screen(
            InputFormModal("Edit preset", fields, initial=initial, submit_label="Save", hints=hints),
            lambda values: self._handle_edit_preset(values, command),
        )

    def _handle_edit_preset(self, values: dict[str, str] | None, command: Command) -> None:
        if not values:
            return
        command_id = values.get("id", "").strip()
        name = values.get("name", "").strip()
        shell = values.get("shell", "").strip()
        if not command_id or not name or not shell:
            self.notify("id, name, and shell are required")
            return
        updated = Command(
            id=command_id,
            name=name,
            description=values.get("description", ""),
            tags=[tag.strip() for tag in values.get("tags", "").split(",") if tag.strip()],
            shell=shell,
            inputs=_build_inputs(shell, values.get("inputs", ""), command.inputs),
            category=values.get("path", "").strip(),
            favorite=command.favorite,
            pinned=command.pinned,
        )
        self.commands = [updated if c.id == command.id else c for c in self.commands]
        try:
            save_commands(self.commands)
        except Exception as exc:  # noqa: BLE001 - surface storage failure
            self.notify(f"save failed: {exc}")
            return
        self._rebuild()
        self._refresh_library_sidebar()
        self.notify("preset saved")

    def action_delete_preset(self) -> None:
        if self.execution_visible:
            return
        command = self.selected_command
        if command is None:
            return
        self.push_screen(
            _ConfirmModal(f"Delete preset {command.id}?", confirm_label="Delete"),
            lambda confirmed: self._handle_delete_preset(confirmed, command),
        )

    def _handle_delete_preset(self, confirmed: bool | None, command: Command) -> None:
        if not confirmed:
            return
        remove_command(command.id)
        self.commands = [c for c in self.commands if c.id != command.id]
        self._rebuild()
        self._refresh_library_sidebar()
        self.notify("preset deleted")

    def action_export_presets(self) -> None:
        if self.execution_visible:
            return
        default_path = Path.home() / ".ambrosia" / "presets-export.json"
        self.push_screen(
            InputFormModal(
                "Export presets",
                [("path", "Export to path", True, False)],
                initial={"path": str(default_path)},
                submit_label="Export",
            ),
            self._handle_export_path,
        )

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
        self.notify(f"exported {len(self.commands)} presets to {raw_path}")

    def action_import_presets(self) -> None:
        if self.execution_visible:
            return
        self.push_screen(
            InputFormModal(
                "Import presets",
                [("path", "Import from path", True, False)],
                submit_label="Import",
            ),
            self._handle_import_path,
        )

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
        self._rebuild()
        self._refresh_library_sidebar()
        self.notify(f"imported {len(merged)} presets")

    def action_save_session(self) -> None:
        self.notify("session is in-memory only; it is cleared when you quit")

    def action_toggle_history(self) -> None:
        self.history_store.enabled = not self.history_store.enabled
        state = "on" if self.history_store.enabled else "off"
        self._refresh_top_bar()
        self.notify(f"history logging {state}")

    def action_toggle_scope(self) -> None:
        if self.scope_policy is None:
            self.scope_policy = load_scope_policy()
        self.scope_policy = replace(self.scope_policy, enabled=not self.scope_policy.enabled)
        save_scope_policy(self.scope_policy)
        self._refresh_top_bar()
        self.notify(f"scope {'on' if self.scope_policy.enabled else 'off'}")

    def action_quit_app(self) -> None:
        if self.running:
            self.push_screen(
                _ConfirmModal("Quit with a job still running?", confirm_label="Quit"),
                self._handle_quit_confirm,
            )
        else:
            self._save_and_exit()

    def _handle_quit_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self._save_and_exit()

    def _save_and_exit(self) -> None:
        # Quitting wipes the session completely: no values survive the process.
        self.session.clear()
        self._session_values.clear()
        self._session_dirty = False
        try:
            SESSION_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        for name in self.session_store.list_sessions():
            try:
                self.session_store.delete_session(name)
            except OSError:
                pass
        self.exit()

    def action_help(self) -> None:
        self.push_screen(_HelpModal())


class _ConfirmModal(ModalScreen[bool]):
    """Ask the operator to confirm a destructive action."""

    CSS = MODAL_CSS

    def __init__(self, message: str, *, confirm_label: str = "Yes") -> None:
        super().__init__()
        self.styles.align = ("center", "middle")
        self._message = message
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._message, id="confirm-message")
            with Horizontal(classes="dialog-actions"):
                yield Static(classes="spacer")
                yield Button(self._confirm_label, id="confirm", variant="primary")
                yield Button("No", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#confirm", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(False)
            event.prevent_default()
            event.stop()


class _ConfirmRunModal(ModalScreen[str | None]):
    """Confirm running a preset with saved values."""

    CSS = MODAL_CSS

    def __init__(self, command: Command, argv: list[str]) -> None:
        super().__init__()
        self.styles.align = ("center", "middle")
        self._command = command
        self._argv = argv

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(f"Run `{' '.join(self._argv)}`? (saved values)", id="confirm-message")
            with Horizontal(classes="dialog-actions"):
                yield Static(classes="spacer")
                yield Button("Run", id="run", variant="primary")
                yield Button("Edit inputs", id="edit")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#run", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        self.dismiss("run" if button_id == "run" else "edit" if button_id == "edit" else None)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.prevent_default()
            event.stop()


class _HelpModal(ModalScreen[None]):
    """Keyboard reference, grouped by category."""

    def __init__(self) -> None:
        super().__init__()
        self.styles.align = ("center", "middle")

    CSS = MODAL_CSS + """
    .dialog {
        width: 78;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Label("Ambrosia v2 — keyboard reference", id="title")
            yield Static(
                "[b]Navigation[/]\n"
                "  [b]/[/b]       focus search bar\n"
                "  [b]Tab[/b]      cycle search → explorer → inspector\n"
                "  [b]Enter[/b]    select / run\n"
                "  [b]Esc[/b]      clear filter / back\n"
                "\n"
                "[b]Search[/]\n"
                "  [b]ctrl+r[/b]   cycle search mode while typing\n"
                "  [b]r[/b]        cycle mode when the explorer has focus\n"
                "  name:windows cmd:nmap tag:discovery path:pr.windows\n"
                "  type:preset | type:workflow | type:all\n"
                "  short form: t:p (presets) | t:w (workflows) | t:a (both)\n"
                "\n"
                "[b]Workflows[/]\n"
                "  workflow definitions live in inventory/workflow/ and can be\n"
                "  found with [b]type:workflow[/]. Enter opens the runner at phase 1.\n"
                "  [b]up/down[/b] pick a command, [b]Enter[/b] runs it,\n"
                "  [b]right[/b] next phase, [b]left[/b] previous (exits on phase 1),\n"
                "  [b]Esc[/b] returns to search.\n"
                "\n"
                "[b]Presets[/]\n"
                "  [b]n[/b] add   [b]e[/b] edit   [b]d[/b] delete   "
                "[b]f[/b] favorite   [b]p[/b] pin\n"
                "  [b]i[/b] import   [b]E[/b] export\n"
                "\n"
                "[b]Execution[/]\n"
                "  [b]c[/b] copy command / cancel running job\n"
                "  [b]x[/b] quick run (minimal result in the inspector)\n"
                "  [b]g[/b] run again   [b]b[/b]/[b]←[/b] back to workstation\n"
                "  [b]s[/b] save session   [b]h[/b] history   [b]S[/b] scope\n"
                "\n"
                "[b]Controls[/]\n"
                "  [b]ctrl+q[/b] quit   [b]?[/b] help\n",
                id="help-text",
            )
            with Horizontal(classes="dialog-actions"):
                yield Static(classes="spacer")
                yield Button("Close", id="close", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#close", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss()

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss()
            event.prevent_default()
            event.stop()


__all__ = ["AmbrosiaApp"]
