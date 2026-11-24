# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Regression tests for the three-panel v2 TUI."""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Button, Input, Static

from ambrosia.model import Command, CommandInput
from ambrosia.tui.app import (
    AmbrosiaApp,
    _ConfirmRunModal,
    _format_input_spec,
    _parse_input_spec,
)
from ambrosia.tui.widgets.input_form import InputFormModal
from ambrosia.tui.widgets.preview import PresetInspector
from ambrosia.tui.widgets.results import PresetExplorer
from ambrosia.tui.widgets.tags import TagBrowser
from ambrosia.workflow import Workflow


def _commands() -> list[Command]:
    return [
        Command(
            id="c1",
            name="nmap scan",
            description="Discover open ports",
            shell="nmap -sV {{target}}",
            inputs=[],
            category="pr.windows.discovery",
            tags=["nmap", "windows"],
        ),
        Command(
            id="c2",
            name="whois lookup",
            description="Look up domain registration",
            shell="whois {{target}}",
            inputs=[],
            category="pr.linux.discovery",
            tags=["whois", "linux"],
        ),
    ]


async def _settled(pilot: object) -> None:
    """Let debounced search and async result population finish."""
    await asyncio.sleep(0.15)  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_three_panels_and_hidden_execution_view() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        assert app.query_one("#library").display is True
        assert app.query_one("#explorer").display is True
        assert app.query_one("#preset-inspector").display is True
        assert app.query_one("#execution-view").display is False
        assert app.query_one("#workflow-view").display is False
        assert app.execution_visible is False
        assert app.workflow_visible is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_sidebar_has_no_namespace_tree_and_populates_tags() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        assert not app.query("#namespace-browser")
        tag_browser = app.query_one("#tag-browser", TagBrowser)
        assert list(tag_browser._tag_checkboxes) == ["linux", "nmap", "whois", "windows"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_first_result_selected_and_inspector_populated() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        explorer = app.query_one("#preset-explorer", PresetExplorer)
        assert explorer.index == 0
        assert app.selected_command is not None
        assert app.selected_command.id == "c1"
        inspector = app.query_one("#preset-inspector", PresetInspector)
        assert "nmap scan" in str(inspector._content.renderable)
        assert not inspector.query("Button")


@pytest.mark.tui
@pytest.mark.asyncio
async def test_result_rows_are_name_description_with_tooltip() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        explorer = app.query_one("#preset-explorer", PresetExplorer)
        first = explorer.children[0]
        assert "nmap scan" in str(first.query_one("Static").renderable)
        assert "Discover open ports" in str(first.query_one("Static").renderable)
        assert "tags:" not in str(first.query_one("Static").renderable)
        assert first.tooltip is not None
        assert "shell:" in str(first.tooltip)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_typing_r_is_preserved_and_ctrl_r_cycles_mode() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        search = app.query_one("#search-bar", Input)
        search.focus()
        for key in "rdp":
            await pilot.press(key)
        await _settled(pilot)
        assert search.value == "rdp"
        assert app.search_mode == "substring"

        search.value = ""
        await _settled(pilot)
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert app.search_mode == "fuzzy"
        assert search.value == ""


@pytest.mark.tui
@pytest.mark.asyncio
async def test_invalid_regex_is_surfaced() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.search_mode = "regex"
        search = app.query_one("#search-bar", Input)
        search.value = "["
        await _settled(pilot)
        assert app.regex_error is not None
        assert "unterminated character set" in app.regex_error
        assert app.filtered_results == []
        assert app.regex_error in str(app.query_one("#search-status").renderable)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_enter_on_explorer_opens_confirm_modal() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, _ConfirmRunModal)
        assert app.focused is not None
        assert app.focused.id == "run"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_library_and_tag_filters() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.query_one("#lib-favorites", Button).press()
        await _settled(pilot)
        assert app.library_view == "favorites"
        assert app.filtered_results == []

        app.query_one("#lib-all", Button).press()
        app.active_tags = ["nmap"]
        app.tag_mode = "or"
        await _settled(pilot)
        assert [result.command.id for result in app.filtered_results] == ["c1"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_arrow_keys_navigate_results_while_search_keeps_focus() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        search = app.query_one("#search-bar", Input)
        search.focus()
        assert app.selected_command is not None
        assert app.selected_command.id == "c1"

        await pilot.press("down")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "search-bar"
        assert search.value == ""
        assert app.selected_command is not None and app.selected_command.id == "c2"

        await pilot.press("up")
        await pilot.pause()
        assert app.selected_command is not None and app.selected_command.id == "c1"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_search_matches_full_words_and_word_fragments() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        search = app.query_one("#search-bar", Input)
        search.value = "win"
        await _settled(pilot)
        # "win" is a fragment of the "windows" tag and category on c1.
        assert [result.command.id for result in app.filtered_results] == ["c1"]
        search.value = "windows"
        await _settled(pilot)
        assert [result.command.id for result in app.filtered_results] == ["c1"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_input_form_is_centered_popup_with_aligned_buttons() -> None:
    commands = [
        Command(
            id="c1",
            name="nmap",
            description="scan",
            shell="nmap {{target}}",
            inputs=[CommandInput(id="target", prompt="Target", required=True)],
            category="pr.windows",
            tags=["nmap"],
        )
    ]
    app = AmbrosiaApp(commands=commands, workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, InputFormModal)
        dialog = app.query_one("#input-form-dialog")
        assert dialog.region.width < 140
        assert dialog.region.x > 0
        submit = app.query_one("#submit", Button)
        cancel = app.query_one("#cancel", Button)
        assert submit.region.x > dialog.region.x + 10
        assert cancel.region.right >= dialog.region.right - 5


@pytest.mark.tui
@pytest.mark.asyncio
async def test_left_arrow_returns_from_execution_view() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.execution_visible = True
        await pilot.pause()
        app.query_one("#execution-log").focus()
        await pilot.press("left")
        await pilot.pause()
        assert app.execution_visible is False
        assert app.query_one("#main-split").display is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_ctrl_q_quits() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert app.is_running is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_dotted_ids_and_tags_do_not_break_widget_ids() -> None:
    commands = [
        Command(
            id="http.observation_18",
            name="http observation",
            description="observe http",
            shell="true",
            inputs=[],
            category="pr.windows",
            tags=["web scanning", "http"],
        )
    ]
    app = AmbrosiaApp(commands=commands, workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        explorer = app.query_one("#preset-explorer", PresetExplorer)
        assert len(explorer.children) == 1
        assert app._filter_task is not None
        assert app._filter_task.exception() is None
        assert app.selected_command is not None
        assert app.selected_command.id == "http.observation_18"
        tag_browser = app.query_one("#tag-browser", TagBrowser)
        assert list(tag_browser._tag_checkboxes) == ["http", "web scanning"]
        assert all(box.id and "." not in box.id for box in tag_browser._tag_checkboxes.values())


@pytest.mark.tui
@pytest.mark.asyncio
async def test_quick_run_shows_minimal_result_in_inspector() -> None:
    commands = [Command(id="c1", name="echo", description="print", shell="printf hello", inputs=[])]
    app = AmbrosiaApp(commands=commands, workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("x")
        await asyncio.sleep(0.4)
        await pilot.pause()
        inspector = app.query_one("#preset-inspector", PresetInspector)
        status = str(inspector._quick_status.renderable)
        assert "exit 0" in status
        assert "hello" in status
        assert app.execution_visible is False
        assert app.query_one("#main-split").display is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_footer_key_map_is_a_single_line() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        footer = app.query_one("#footer")
        assert footer.region.height == 1
        rendered = str(footer.renderable)
        assert "\n" not in rendered
        assert "/:search" in rendered
        assert "?:help" in rendered


@pytest.mark.tui
@pytest.mark.asyncio
async def test_tab_cycles_focus_between_regions() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        assert app.focused is not None and app.focused.id == "preset-explorer"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "search-bar"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "preset-explorer"


def test_input_spec_round_trip() -> None:
    spec = "target:Target IP:host, password::secret+optional, user:Username"
    overrides = _parse_input_spec(spec)
    assert set(overrides) == {"target", "password", "user"}
    assert overrides["target"].prompt == "Target IP"
    assert overrides["target"].type == "host"
    assert overrides["password"].prompt == "password"
    assert overrides["password"].required is False
    assert overrides["password"].secret is True
    assert overrides["user"].type == "string"
    assert _parse_input_spec(_format_input_spec(list(overrides.values()))) == overrides


@pytest.mark.tui
@pytest.mark.asyncio
async def test_add_preset_derives_inputs_from_shell_placeholders(monkeypatch) -> None:
    added: list[Command] = []
    monkeypatch.setattr("ambrosia.tui.app.add_command", added.append)
    app = AmbrosiaApp(commands=_commands(), workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_add_preset()
        await pilot.pause()
        assert isinstance(app.screen, InputFormModal)
        app.query_one("#input-id", Input).value = "new-one"
        app.query_one("#input-name", Input).value = "New preset"
        app.query_one("#input-shell", Input).value = "nmap {{target}} --port {{port}}"
        app.query_one("#input-inputs", Input).value = "target:Target IP:host, port::optional"
        app.query_one("#submit", Button).press()
        await pilot.pause()

        assert len(added) == 1
        command = added[0]
        # Placeholders become inputs, even when the spec only customizes some.
        assert [inp.id for inp in command.inputs] == ["target", "port"]
        assert command.inputs[0].prompt == "Target IP"
        assert command.inputs[0].type == "host"
        assert command.inputs[1].prompt == "port"
        assert command.inputs[1].required is False
        assert any(c.id == "new-one" for c in app.commands)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_edit_preset_picks_up_new_placeholders_and_keeps_existing(monkeypatch) -> None:
    saved: list[list[Command]] = []
    monkeypatch.setattr("ambrosia.tui.app.save_commands", saved.append)
    original = Command(
        id="c1",
        name="scan",
        description="scan",
        shell="nmap {{target}}",
        inputs=[CommandInput(id="target", prompt="Target IP", type="host")],
    )
    app = AmbrosiaApp(commands=[original], workflows=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_edit_preset()
        await pilot.pause()
        assert isinstance(app.screen, InputFormModal)
        # Existing input definition is round-tripped into the spec field.
        assert app.query_one("#input-inputs", Input).value == "target:Target IP:host"
        app.query_one("#input-shell", Input).value = "nmap {{target}} -p {{port}}"
        app.query_one("#input-inputs", Input).value = "port:Port:integer"
        app.query_one("#submit", Button).press()
        await pilot.pause()

        assert saved
        updated = saved[-1][0]
        # The original target definition survives even though it was omitted
        # from the spec; the new placeholder is added with defaults.
        assert [inp.id for inp in updated.inputs] == ["target", "port"]
        assert updated.inputs[0].prompt == "Target IP"
        assert updated.inputs[0].type == "host"
        assert updated.inputs[1].type == "integer"


def _workflows() -> list[Workflow]:
    return [
        Workflow(
            name="Linux Recon",
            id="linux-recon",
            description="Read-only Linux reconnaissance chain.",
            phases={
                "discovery": ["linux.nmap.discovery", "linux.ssh.version"],
                "exposure": ["windows.rdp.exposure"],
            },
        )
    ]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_type_workflow_surfaces_workflows_in_explorer_and_inspector() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=_workflows())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        search = app.query_one("#search-bar", Input)
        search.value = "type:workflow"
        await _settled(pilot)

        assert len(app.filtered_results) == 1
        result = app.filtered_results[0]
        assert result.workflow is not None and result.workflow.id == "linux-recon"
        assert app.selected_workflow is result.workflow
        assert app.selected_command is None

        explorer = app.query_one("#preset-explorer", PresetExplorer)
        assert len(explorer.children) == 1
        label = str(explorer.children[0].query_one(Static).renderable)
        assert "Linux Recon" in label and "[workflow]" in label

        inspector = app.query_one("#preset-inspector", PresetInspector)
        rendered = str(inspector._content.renderable)
        assert "phases" in rendered
        assert "linux.nmap.discovery" in rendered
        assert "exposure" in rendered
        assert str(inspector._title.renderable) == "WORKFLOW INSPECTOR"
        assert not inspector.query("Button")


@pytest.mark.tui
@pytest.mark.asyncio
async def test_type_all_shows_both_kinds_and_workflow_enter_is_safe() -> None:
    app = AmbrosiaApp(commands=_commands(), workflows=_workflows())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.query_one("#search-bar", Input).value = "type:all"
        await _settled(pilot)
        assert len(app.filtered_results) == 3
        assert {type(result.item) for result in app.filtered_results} == {Command, Workflow}

        # Highlight the workflow row, then activate it: it should only update
        # the inspector, never start a subprocess or switch views.
        explorer = app.query_one("#preset-explorer", PresetExplorer)
        workflow_index = next(
            index
            for index, child in enumerate(explorer.children)
            if str(child.id or "").startswith("workflow_")
        )
        explorer.index = workflow_index
        await pilot.pause()
        app.action_focus_explorer()
        await pilot.press("enter")
        await pilot.pause()
        assert app.execution_visible is False
        assert app.running is False
        assert app.selected_workflow is not None
        assert app.selected_workflow.id == "linux-recon"


def _workflow_commands() -> list[Command]:
    return [
        Command(id="cmd.one", name="Echo one", description="one", shell="printf one", inputs=[]),
        Command(id="cmd.two", name="Echo two", description="two", shell="printf two", inputs=[]),
        Command(
            id="cmd.three", name="Echo three", description="three", shell="printf three", inputs=[]
        ),
    ]


def _chain_workflow() -> list[Workflow]:
    return [
        Workflow(
            name="Test Chain",
            id="test-chain",
            description="demo chain",
            phases={
                "phase one": ["cmd.one", "cmd.two"],
                "phase two": ["cmd.three"],
            },
        )
    ]


async def _open_workflow(pilot: object, app: AmbrosiaApp) -> None:
    app.query_one("#search-bar", Input).value = "type:workflow"
    await _settled(pilot)
    app.action_focus_explorer()
    await pilot.pause()  # type: ignore[attr-defined]
    await pilot.press("enter")  # type: ignore[attr-defined]
    await asyncio.sleep(0.2)
    await pilot.pause()  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_enter_opens_phase_one() -> None:
    app = AmbrosiaApp(commands=_workflow_commands(), workflows=_chain_workflow())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await _open_workflow(pilot, app)

        assert app.workflow_visible is True
        assert app.active_workflow is not None and app.active_workflow.id == "test-chain"
        assert app.workflow_phase_index == 0
        assert app.query_one("#main-split").display is False
        assert app.query_one("#workflow-view").display is True
        assert app.focused is not None and app.focused.id == "workflow-commands"
        rows = app.query_one("#workflow-commands")
        assert len(rows.children) == 2
        assert "Echo one" in str(rows.children[0].query_one(Static).renderable)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_arrows_switch_phases_and_left_exits() -> None:
    app = AmbrosiaApp(commands=_workflow_commands(), workflows=_chain_workflow())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await _open_workflow(pilot, app)

        await pilot.press("right")
        await asyncio.sleep(0.15)
        await pilot.pause()
        assert app.workflow_phase_index == 1
        rows = app.query_one("#workflow-commands")
        assert len(rows.children) == 1
        assert "Echo three" in str(rows.children[0].query_one(Static).renderable)

        await pilot.press("right")
        await asyncio.sleep(0.15)
        await pilot.pause()
        assert app.workflow_phase_index == 1  # clamped at the last phase

        await pilot.press("left")
        await asyncio.sleep(0.15)
        await pilot.pause()
        assert app.workflow_phase_index == 0
        await pilot.press("left")
        await asyncio.sleep(0.15)
        await pilot.pause()
        # Left on phase 1 acts like Esc and returns to the main TUI.
        assert app.workflow_visible is False
        assert app.active_workflow is None
        assert app.query_one("#main-split").display is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_command_runs_and_back_returns_to_phase() -> None:
    app = AmbrosiaApp(commands=_workflow_commands(), workflows=_chain_workflow())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await _open_workflow(pilot, app)

        await pilot.press("enter")
        await pilot.pause()
        assert type(app.screen).__name__ == "_ConfirmRunModal"
        await pilot.press("enter")
        await asyncio.sleep(0.4)
        await pilot.pause()
        assert app.execution_visible is True
        assert app.workflow_visible is True

        await pilot.press("left")
        await asyncio.sleep(0.2)
        await pilot.pause()
        assert app.execution_visible is False
        assert app.workflow_visible is True
        assert app.workflow_phase_index == 0
        assert app.query_one("#workflow-view").display is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_escape_returns_to_workstation() -> None:
    app = AmbrosiaApp(commands=_workflow_commands(), workflows=_chain_workflow())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await _open_workflow(pilot, app)
        await pilot.press("escape")
        await pilot.pause()
        assert app.workflow_visible is False
        assert app.active_workflow is None
        assert app.query_one("#main-split").display is True
