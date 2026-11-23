# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Extensive TUI-only coverage: widgets, parsing, state, and interactions.

This module deliberately tests only Python TUI code. It does not read or
validate markdown, YAML, ``.preset``, or ``.workflow`` files; workflow and
preset objects here are plain in-memory Python fixtures.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import TYPE_CHECKING

import pytest
from textual.widgets import Button, Input, RadioButton, Static

from ambrosia.model import Command, CommandInput
from ambrosia.scope import ScopePolicy
from ambrosia.tui.app import (
    SESSION_FILE,
    AmbrosiaApp,
    _build_inputs,
    _ConfirmModal,
    _ConfirmRunModal,
    _format_input_spec,
    _parse_input_spec,
)
from ambrosia.tui.design import (
    AMBER,
    DARK_PANEL_BG,
    DEEP_PANEL_BG,
    FEMME_PINK,
    GUMMY_AMBER,
    GUMMY_GREEN,
    GUMMY_LIGHT_PINK,
    GUMMY_PINK,
    GUMMY_RED,
    HOVER_BG,
    PHOSPHOR,
    PHOSPHOR_CYAN,
    SELECTED_BG,
    TEXT_MUTED,
    TEXT_PRIMARY,
    YELLOW,
)
from ambrosia.tui.ids import safe_widget_id
from ambrosia.tui.matching import (
    SearchQuery,
    match_command,
    match_workflow,
    parse_search_query,
    regex_error,
    search_commands,
    search_items,
    search_workflows,
)
from ambrosia.tui.widgets.execution_view import ExecutionView
from ambrosia.tui.widgets.input_form import InputFormModal
from ambrosia.tui.widgets.preview import PresetInspector
from ambrosia.tui.widgets.results import PresetExplorer
from ambrosia.tui.widgets.search import SearchBar
from ambrosia.tui.widgets.tags import TagBrowser
from ambrosia.tui.widgets.workflow_view import WorkflowView
from ambrosia.workflow import Workflow

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


# --------------------------------------------------------------------------- helpers


def _commands() -> list[Command]:
    return [
        Command(
            id="c1",
            name="nmap scan",
            description="Discover open ports",
            shell="nmap -sV {{target}}",
            category="pr.windows.discovery",
            tags=["nmap", "windows"],
            favorite=True,
        ),
        Command(
            id="c2",
            name="whois lookup",
            description="Look up domain registration",
            shell="whois {{target}}",
            category="pr.linux.discovery",
            tags=["whois", "linux"],
            pinned=True,
        ),
    ]


def _workflows() -> list[Workflow]:
    return [
        Workflow(
            name="Chain",
            id="chain",
            description="demo",
            phases={"one": ["c1"], "two": ["c2"]},
        )
    ]


def _app(commands: list[Command] | None = None, workflows: list[Workflow] | None = None) -> AmbrosiaApp:
    return AmbrosiaApp(
        commands=_commands() if commands is None else commands,
        workflows=[] if workflows is None else workflows,
    )


async def _settled(pilot: object) -> None:
    await asyncio.sleep(0.12)  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]


# =========================================================================== ids.py


def test_safe_widget_id_keeps_valid_values() -> None:
    assert safe_widget_id("already_valid-1") == "already_valid-1"


def test_safe_widget_id_replaces_invalid_characters() -> None:
    assert safe_widget_id("http.observation_18") == "http_observation_18"
    assert safe_widget_id("web scanning") == "web_scanning"


def test_safe_widget_id_prefixes_leading_digit() -> None:
    assert safe_widget_id("18scan") == "id_18scan"


def test_safe_widget_id_handles_empty_and_all_invalid() -> None:
    assert safe_widget_id("") == "id_"
    assert safe_widget_id("...") == "id_"


def test_safe_widget_id_trips_surrounding_underscores() -> None:
    assert safe_widget_id("__tag__") == "tag"


def test_safe_widget_id_always_matches_textual_rules() -> None:
    for raw in ("a.b c", "42", "-", "a/b\\c", "x" * 50):
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", safe_widget_id(raw))


# ======================================================================== design.py


def test_palette_exports_are_six_digit_hex() -> None:
    colors = {
        AMBER,
        DARK_PANEL_BG,
        DEEP_PANEL_BG,
        FEMME_PINK,
        GUMMY_AMBER,
        GUMMY_GREEN,
        GUMMY_LIGHT_PINK,
        GUMMY_PINK,
        GUMMY_RED,
        HOVER_BG,
        PHOSPHOR,
        PHOSPHOR_CYAN,
        SELECTED_BG,
        TEXT_MUTED,
        TEXT_PRIMARY,
        YELLOW,
    }
    assert all(re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in colors)


def test_palette_aliases_are_consistent() -> None:
    assert GUMMY_GREEN == PHOSPHOR == PHOSPHOR_CYAN
    assert GUMMY_AMBER == AMBER


def test_palette_has_no_cold_blue_or_aubergine() -> None:
    for color in (DARK_PANEL_BG, DEEP_PANEL_BG, SELECTED_BG, HOVER_BG):
        red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        assert red >= blue, color
        assert green <= red or color == DEEP_PANEL_BG


# ======================================================================= matching.py


def test_parse_search_query_all_qualifiers() -> None:
    query = parse_search_query("name:scan cmd:nmap tag:windows path:pr.windows type:all")
    assert query.qualifiers == {
        "name": "scan",
        "cmd": "nmap",
        "tag": "windows",
        "path": "pr.windows",
        "type": "all",
    }
    assert query.free_text == ""


def test_parse_search_query_duplicate_qualifier_last_wins() -> None:
    query = parse_search_query("name:first name:second free text")
    assert query.qualifiers == {"name": "second"}
    assert query.free_text == "free text"


def test_search_query_is_empty() -> None:
    assert SearchQuery(raw="").is_empty()
    assert SearchQuery(raw="   ").is_empty()
    assert not SearchQuery(raw="x").is_empty()


def test_regex_error_checks_free_text_and_qualifiers() -> None:
    assert regex_error(parse_search_query("nmap", "regex")) is None
    assert regex_error(parse_search_query("[", "regex")) is not None
    assert regex_error(parse_search_query("name:(", "regex")) is not None
    # type: is a meta qualifier, never a regex pattern.
    assert regex_error(parse_search_query("type:workflow", "regex")) is None


def test_match_command_empty_query_is_neutral() -> None:
    result = match_command(_commands()[0], parse_search_query(""))
    assert result is not None
    assert result.rank == 0
    assert result.matched_fields == ()
    assert result.tiebreaker == 0


def test_match_command_qualifier_mismatch_returns_none() -> None:
    assert match_command(_commands()[0], parse_search_query("name:whois")) is None
    assert match_command(_commands()[0], parse_search_query("tag:linux")) is None


def test_match_command_matches_description() -> None:
    assert match_command(_commands()[0], parse_search_query("registration")) is None
    assert match_command(_commands()[1], parse_search_query("registration")) is not None


def test_multi_word_free_text_matches_across_fields() -> None:
    both = Command(
        id="nla",
        name="Disable NLA",
        description="Disable Network Level Authentication for RDP via registry.",
        shell="reg add ...",
        tags=["windows", "rdp"],
        category="windows",
    )
    registry_only = Command(
        id="registry-only",
        name="Registry tweak",
        description="Edit the registry",
        shell="reg add ...",
        tags=[],
        category="windows",
    )
    rdp_only = Command(
        id="rdp-only",
        name="RDP exposure",
        description="Check RDP port",
        shell="nmap -p 3389 {{target}}",
        tags=["rdp"],
        category="windows",
    )
    commands = [both, registry_only, rdp_only]
    results = search_commands(commands, parse_search_query("regis rdp"))
    assert [result.command.id for result in results] == ["nla"]


def test_multi_word_free_text_in_fuzzy_mode() -> None:
    command = _commands()[0]
    assert match_command(command, parse_search_query("nmap disc", "fuzzy")) is not None
    assert match_command(command, parse_search_query("nmap zzz", "fuzzy")) is None


def test_regex_mode_keeps_multi_word_pattern_whole() -> None:
    reversed_name = Command(
        id="reversed", name="version windows", description="", shell="", tags=[], category=""
    )
    assert match_command(reversed_name, parse_search_query("windows version", "regex")) is None


def test_match_command_word_start_ranks_ahead_of_buried_match() -> None:
    commands = [
        Command(id="a", name="xwindows", description="", shell="", category=""),
        Command(id="b", name="windows scan", description="", shell="", category=""),
    ]
    results = search_commands(commands, parse_search_query("win"))
    assert [result.command.id for result in results] == ["b", "a"]


def test_match_command_fuzzy_mode() -> None:
    result = match_command(_commands()[0], parse_search_query("nmsc", "fuzzy"))
    assert result is not None


def test_match_command_regex_mode() -> None:
    assert match_command(_commands()[0], parse_search_query("^nmap", "regex")) is not None
    assert match_command(_commands()[0], parse_search_query("^whois", "regex")) is None


def test_search_commands_is_sorted_and_keeps_result_properties() -> None:
    results = search_commands(_commands(), parse_search_query(""))
    assert len(results) == 2
    assert all(result.command is not None and result.workflow is None for result in results)
    assert [result.rank for result in results] == sorted(result.rank for result in results)


def test_match_workflow_fields_and_type_gating() -> None:
    workflow = _workflows()[0]
    assert match_workflow(workflow, parse_search_query("chain")) is not None
    assert match_workflow(workflow, parse_search_query("id:chain")) is None  # no id: qualifier
    assert match_workflow(workflow, parse_search_query("t:w")) is not None
    assert match_workflow(workflow, parse_search_query("t:p")) is None
    result = match_workflow(workflow, parse_search_query(""))
    assert result is not None and result.workflow is workflow and result.command is None


def test_search_workflows_matches_phase_command_ids() -> None:
    assert search_workflows(_workflows(), parse_search_query("cmd:c2")) != []
    assert search_workflows(_workflows(), parse_search_query("nothing here")) == []


def test_search_items_respects_type_filters() -> None:
    commands, workflows = _commands(), _workflows()
    assert all(r.workflow is None for r in search_items(commands, workflows, parse_search_query("t:p")))
    assert all(r.command is None for r in search_items(commands, workflows, parse_search_query("t:w")))
    assert len(search_items(commands, workflows, parse_search_query("t:a"))) == 3


# ====================================================================== app helpers


def test_parse_input_spec_empty_and_unknown_flags() -> None:
    assert _parse_input_spec("") == {}
    overrides = _parse_input_spec("x::weird+flag")
    assert overrides["x"].required is True
    assert overrides["x"].secret is False
    assert overrides["x"].type == "string"


def test_format_input_spec_defaults() -> None:
    inputs = [
        CommandInput(id="a", prompt="a"),
        CommandInput(id="b", prompt="Prompt B", type="host", required=False, secret=True),
    ]
    assert _format_input_spec(inputs) == "a, b:Prompt B:optional+secret+host"


def test_build_inputs_keeps_order_and_ignores_orphan_specs() -> None:
    existing = [CommandInput(id="target", prompt="Target IP", type="host")]
    inputs = _build_inputs(
        "nmap {{target}} -p {{port}}", "target:New Prompt, ghost:Ghost", existing
    )
    assert [item.id for item in inputs] == ["target", "port"]
    assert inputs[0].prompt == "New Prompt"  # explicit spec overrides existing
    assert inputs[1].prompt == "port"


def test_build_inputs_explicit_spec_overrides_existing() -> None:
    existing = [CommandInput(id="target", prompt="Old", type="host")]
    inputs = _build_inputs("nmap {{target}}", "target:New:secret", existing)
    assert inputs[0].prompt == "New"
    assert inputs[0].secret is True


def test_values_for_and_remember_values_share_by_input_name() -> None:
    app = _app()
    first = Command(id="a", name="a", description="", shell="nmap {{target}}", inputs=[CommandInput(id="target", prompt="t")])
    second = Command(id="b", name="b", description="", shell="whois {{target}} {{user}}", inputs=[CommandInput(id="target", prompt="t"), CommandInput(id="user", prompt="u")])
    app._remember_values(first, {"target": "10.0.0.1"})
    assert app._values_for(second)["target"] == "10.0.0.1"
    assert app._missing_required(second, app._values_for(second)) is True
    app._remember_values(second, {"target": "10.0.0.1", "user": "alice"})
    assert app._missing_required(second, app._values_for(second)) is False


def test_extract_scope_target_prefers_named_target_then_any_ip() -> None:
    command = Command(id="c", name="c", description="", shell="", inputs=[CommandInput(id="target", prompt="t"), CommandInput(id="other", prompt="o")])
    assert AmbrosiaApp._extract_scope_target(command, {"target": "10.0.0.5"}) == "10.0.0.5"
    assert AmbrosiaApp._extract_scope_target(command, {"other": "10.0.0.6"}) == "10.0.0.6"
    assert AmbrosiaApp._extract_scope_target(command, {"target": "hostname"}) is None


# =============================================================== InputFormModal


@pytest.mark.tui
@pytest.mark.asyncio
async def test_input_form_renders_markers_hints_and_secret_fields() -> None:
    app = _app()
    fields = [("target", "Target", True, False), ("pw", "Password", True, True), ("note", "Note", False, False)]
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.push_screen(InputFormModal("Form", fields, hints={"target": "an IP"}))
        await pilot.pause()
        assert "Target" in str(app.query_one("#label-target", Static).renderable)
        assert "optional" in str(app.query_one("#label-note", Static).renderable)
        assert app.query_one("#input-pw", Input).password is True
        assert app.query_one("#input-target", Input).password is False
        assert "an IP" in str(app.query_one("#hint-target", Static).renderable)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_input_form_prefills_and_focuses_first_field() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.push_screen(
            InputFormModal("Form", [("a", "A", True, False), ("b", "B", True, False)], initial={"a": "one"})
        )
        await pilot.pause()
        assert app.query_one("#input-a", Input).value == "one"
        assert app.query_one("#input-b", Input).value == ""
        assert app.focused is not None and app.focused.id == "input-a"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_input_form_with_no_fields_focuses_submit() -> None:
    app = _app()
    captured: list[dict[str, str]] = []
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.push_screen(InputFormModal("Empty", []), captured.append)
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "submit"
        app.query_one("#submit", Button).press()
        await pilot.pause()
        assert captured == [{}]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_input_form_enter_submits_values() -> None:
    app = _app()
    captured: list[dict[str, str]] = []
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.push_screen(InputFormModal("Form", [("a", "A", True, False)]), captured.append)
        await pilot.pause()
        app.query_one("#input-a", Input).value = "typed"
        await pilot.press("enter")
        await pilot.pause()
        assert captured == [{"a": "typed"}]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_input_form_cancel_and_escape_dismiss_none() -> None:
    for _key, button_id in (("escape", None), (None, "cancel")):
        app = _app()
        captured: list[dict[str, str] | None] = []
        async with app.run_test(size=(140, 45)) as pilot:
            await _settled(pilot)
            app.push_screen(InputFormModal("Form", [("a", "A", True, False)]), captured.append)
            await pilot.pause()
            if button_id:
                app.query_one(f"#{button_id}", Button).press()
            else:
                await pilot.press("escape")
            await pilot.pause()
            assert captured == [None]


# ==================================================================== modal screens


@pytest.mark.tui
@pytest.mark.asyncio
async def test_confirm_modal_yes_no_and_escape() -> None:
    for action, expected in (("confirm", True), ("cancel", False), ("escape", False)):
        app = _app()
        captured: list[bool] = []
        async with app.run_test(size=(140, 45)) as pilot:
            await _settled(pilot)
            app.push_screen(_ConfirmModal("Sure?"), captured.append)
            await pilot.pause()
            assert app.focused is not None and app.focused.id == "confirm"
            if action == "escape":
                await pilot.press("escape")
            else:
                app.query_one(f"#{action}", Button).press()
            await pilot.pause()
            assert captured == [expected]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_confirm_run_modal_buttons_map_to_outcomes() -> None:
    command = _commands()[0]
    for button_id, expected in (("run", "run"), ("edit", "edit"), ("cancel", None)):
        app = _app()
        captured: list[str | None] = []
        async with app.run_test(size=(140, 45)) as pilot:
            await _settled(pilot)
            app.push_screen(_ConfirmRunModal(command, ["nmap", "-sV", "1.2.3.4"]), captured.append)
            await pilot.pause()
            app.query_one(f"#{button_id}", Button).press()
            await pilot.pause()
            assert captured == [expected]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_help_modal_opens_and_closes() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_help()
        await pilot.pause()
        assert type(app.screen).__name__ == "_HelpModal"
        assert "keyboard reference" in str(app.query_one("#title", Static).renderable)
        await pilot.press("escape")
        await pilot.pause()
        assert len(app.screen_stack) == 1


@pytest.mark.tui
@pytest.mark.asyncio
async def test_check_action_disabled_while_modal_is_open() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        assert app.check_action("quit_app", ()) is True
        app.action_help()
        await pilot.pause()
        assert app.check_action("quit_app", ()) is False


# ==================================================================== PresetExplorer


@pytest.mark.tui
@pytest.mark.asyncio
async def test_explorer_handles_empty_results() -> None:
    app = _app(commands=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        explorer = app.query_one("#preset-explorer", PresetExplorer)
        assert len(explorer.children) == 0
        assert explorer.index is None
        assert explorer.selected_item() is None
        assert app.selected_command is None


@pytest.mark.tui
@pytest.mark.asyncio
async def test_explorer_generates_unique_ids_for_duplicate_command_ids() -> None:
    commands = [
        Command(id="same", name="first", description="", shell="true", category="a"),
        Command(id="same", name="second", description="", shell="true", category="b"),
    ]
    app = _app(commands=commands)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        explorer = app.query_one("#preset-explorer", PresetExplorer)
        ids = [child.id for child in explorer.children]
        assert len(set(ids)) == 2
        assert app._filter_task is not None and app._filter_task.exception() is None


@pytest.mark.tui
@pytest.mark.asyncio
async def test_explorer_tooltips_show_command_details() -> None:
    commands = [
        Command(
            id="c",
            name="Full",
            description="desc",
            shell="tool {{target}}",
            category="path.here",
            tags=["a", "b"],
            inputs=[CommandInput(id="target", prompt="Target", required=True, secret=True)],
        )
    ]
    app = _app(commands=commands)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        tooltip = str(app.query_one("#preset-explorer").children[0].tooltip)
        for expected in ("id: c", "path: path.here", "tags: a, b", "tool {{target}}", "secret", "Target"):
            assert expected in tooltip


@pytest.mark.tui
@pytest.mark.asyncio
async def test_explorer_workflow_tooltip_shows_phases() -> None:
    app = _app(commands=[], workflows=_workflows())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.query_one("#search-bar", Input).value = "t:w"
        await _settled(pilot)
        tooltip = str(app.query_one("#preset-explorer").children[0].tooltip)
        assert "id: chain" in tooltip
        assert "demo" in tooltip
        assert "one:" in tooltip and "c1" in tooltip


# =================================================================== PresetInspector


@pytest.mark.tui
@pytest.mark.asyncio
async def test_inspector_placeholder_disables_buttons() -> None:
    app = _app(commands=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        inspector = app.query_one("#preset-inspector", PresetInspector)
        assert "No preset" in str(inspector._content.renderable)
        assert all(
            button.disabled
            for button in (inspector._run_button, inspector._favorite_button, inspector._pin_button)
        )


@pytest.mark.tui
@pytest.mark.asyncio
async def test_inspector_shows_favorite_pin_markers_and_secret_masking() -> None:
    commands = [
        Command(
            id="c",
            name="Secure",
            description="desc",
            shell="tool {{pw}}",
            favorite=True,
            pinned=True,
            inputs=[CommandInput(id="pw", prompt="Password", secret=True, validation_hint="secret hint")],
        )
    ]
    app = _app(commands=commands)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        inspector = app.query_one("#preset-inspector", PresetInspector)
        rendered = str(inspector._content.renderable)
        assert "★" in rendered and "▲" in rendered
        assert "(not set)" in rendered
        assert str(inspector._favorite_button.label) == "UNFAVORITE"
        assert str(inspector._pin_button.label) == "UNPIN"
        app._remember_values(commands[0], {"pw": "hunter2"})
        inspector.set_command(commands[0], app._values_for(commands[0]))
        assert "********" in str(inspector._content.renderable)
        assert "hunter2" not in str(inspector._content.renderable)
        assert "secret hint" in str(inspector._content.renderable)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_inspector_quick_status_is_set_and_cleared() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        inspector = app.query_one("#preset-inspector", PresetInspector)
        inspector.set_quick_status("exit 0 · done")
        assert "exit 0" in str(inspector._quick_status.renderable)
        app.selected_item = None
        await pilot.pause()
        assert str(inspector._quick_status.renderable) == ""


@pytest.mark.tui
@pytest.mark.asyncio
async def test_inspector_workflow_view_disables_actions() -> None:
    app = _app(commands=[], workflows=_workflows())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.selected_item = _workflows()[0]
        await pilot.pause()
        inspector = app.query_one("#preset-inspector", PresetInspector)
        assert str(inspector._title.renderable) == "WORKFLOW INSPECTOR"
        assert all(
            button.disabled
            for button in (inspector._run_button, inspector._favorite_button, inspector._pin_button)
        )


@pytest.mark.tui
@pytest.mark.asyncio
async def test_inspector_buttons_post_messages(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    monkeypatch.setattr("ambrosia.tui.app.save_commands", lambda _commands: None)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.query_one("#inspector-favorite", Button).press()
        await pilot.pause()
        assert app.commands[0].favorite is False  # fixture started favorite=True
        app.query_one("#inspector-pin", Button).press()
        await pilot.pause()
        assert app.commands[0].pinned is True  # fixture started pinned=False


# ==================================================================== TagBrowser


@pytest.mark.tui
@pytest.mark.asyncio
async def test_tag_browser_counts_active_state_and_id_map() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        browser = app.query_one("#tag-browser", TagBrowser)
        assert browser._tag_checkboxes["nmap"].label.plain.startswith("nmap")
        browser.set_tags({"nmap": 1, "web scanning": 2}, active_tags=["nmap"])
        await asyncio.sleep(0.1)
        await pilot.pause()
        assert browser._tag_checkboxes["nmap"].value is True
        assert browser._tag_checkboxes["web scanning"].value is False
        assert browser._id_to_tag["tag-web_scanning"] == "web scanning"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_tag_browser_checkbox_and_mode_emit_changes() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        browser = app.query_one("#tag-browser", TagBrowser)
        browser._tag_checkboxes["nmap"].value = True
        await pilot.pause()
        assert app.active_tags == ["nmap"]
        app.query_one("#tag-mode-and", RadioButton).value = True
        await pilot.pause()
        assert app.tag_mode == "and"


# ==================================================================== SearchBar


@pytest.mark.tui
@pytest.mark.asyncio
async def test_search_bar_parses_and_focuses_cursor_at_end() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        bar = app.query_one("#search-bar", SearchBar)
        bar.value = "tag:nmap"
        assert bar.parsed_query().qualifiers == {"tag": "nmap"}
        bar.value = "abc"
        bar.focus_input()
        assert bar.cursor_position == 3
        assert bar.has_focus


@pytest.mark.tui
@pytest.mark.asyncio
async def test_search_bar_cycles_all_modes_and_wraps() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        for expected in ("fuzzy", "regex", "substring"):
            await pilot.press("ctrl+r")
            await pilot.pause()
            assert app.search_mode == expected
            assert expected in str(app.query_one("#search-mode-indicator", Static).renderable)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_search_bar_enter_and_tab_focus_explorer() -> None:
    for key in ("enter", "tab"):
        app = _app()
        async with app.run_test(size=(140, 45)) as pilot:
            await _settled(pilot)
            assert app.focused is not None and app.focused.id == "search-bar"
            await pilot.press(key)
            await pilot.pause()
            assert app.focused is not None and app.focused.id == "preset-explorer"


# ================================================================ ExecutionView


@pytest.mark.tui
@pytest.mark.asyncio
async def test_execution_view_start_write_and_finish_success() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        view = app.query_one("#execution-view", ExecutionView)
        view.start("echo", ["echo", "hi"])
        view.write_line("hello")
        view.finish(0, 250)
        await pilot.pause()
        assert "running:" in str(view._header.renderable)
        assert "hello" in str(view._log.lines)
        assert "exit code: 0" in str(view._status.renderable)
        assert view._run_again.display is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_execution_view_failure_and_cancel_status() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        view = app.query_one("#execution-view", ExecutionView)
        view.start("x", ["x"])
        view.finish(7, 10)
        assert "exit code: 7" in str(view._status.renderable)
        view.start("x", ["x"])
        view.finish(None, 0, cancelled=True)
        assert "cancelled" in str(view._status.renderable)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_execution_view_run_again_button_calls_action(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    calls: list[int] = []
    monkeypatch.setattr(app, "action_run_again", lambda: calls.append(1))
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.query_one("#run-again", Button).press()
        await pilot.pause()
        assert calls == [1]


# ================================================================ WorkflowView


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_view_renders_phase_rows_and_missing_presets() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        view = app.query_one("#workflow-view", WorkflowView)
        workflow = Workflow(name="W", id="w", phases={"p1": ["c1", "missing"]})
        await view.set_workflow(workflow, {"c1": _commands()[0]}, 0, 0)
        rows = view._commands
        assert len(rows.children) == 2
        assert "preset not found" in str(rows.children[1].query_one(Static).renderable)
        assert view.selected_command_id() == "c1"
        assert view.selected_index() == 0
        app.workflow_visible = True
        await pilot.pause()
        view.focus_list()
        assert app.focused is not None and app.focused.id == "workflow-commands"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_view_handles_no_phases() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        view = app.query_one("#workflow-view", WorkflowView)
        await view.set_workflow(Workflow(name="Empty", id="empty"), {}, 0, 0)
        assert "no phases" in str(view._phase.renderable)
        assert len(view._commands.children) == 0
        assert view.selected_command_id() is None


# ============================================================== app top bar / footer


@pytest.mark.tui
@pytest.mark.asyncio
async def test_top_bar_shows_all_indicators(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    monkeypatch.setattr(
        "ambrosia.tui.app.load_scope_policy", lambda: ScopePolicy(enabled=True, mode="denylist")
    )
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.active_tags = ["nmap"]
        app.history_store.enabled = True
        app.scope_policy = ScopePolicy(enabled=True, mode="denylist")
        app.query_one("#search-bar", Input).value = "t:w"
        await _settled(pilot)
        rendered = app.query_one("#top-bar-left", Static).renderable.plain
        assert "WORKFLOWS 0" in rendered
        assert "RESULTS" in rendered
        assert "tag: nmap" in rendered
        assert "scope: on" in rendered
        assert "history: on" in rendered
        assert "type: workflow" in rendered


@pytest.mark.tui
@pytest.mark.asyncio
async def test_footer_truncates_on_narrow_terminal() -> None:
    app = _app()
    async with app.run_test(size=(60, 20)) as pilot:
        await _settled(pilot)
        footer = app.query_one("#footer", Static)
        rendered = str(footer.renderable)
        assert "\n" not in rendered
        assert len(rendered) <= 58
        assert "/:search" in rendered
        assert "…" in rendered  # trimmed, full map lives in "?" help


@pytest.mark.tui
@pytest.mark.asyncio
async def test_top_bar_shows_running_state() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.running = True
        await pilot.pause()
        assert "RUNNING" in app.query_one("#top-bar-left", Static).renderable.plain


# ================================================================ app interactions


@pytest.mark.tui
@pytest.mark.asyncio
async def test_library_button_states_follow_view() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.query_one("#lib-pinned", Button).press()
        await pilot.pause()
        assert app.library_view == "pinned"
        assert app.query_one("#lib-pinned", Button).has_class("--active")
        assert not app.query_one("#lib-all", Button).has_class("--active")


@pytest.mark.tui
@pytest.mark.asyncio
async def test_favorite_and_pin_toggle_persist(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    saved: list[list[Command]] = []
    monkeypatch.setattr("ambrosia.tui.app.save_commands", saved.append)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("p")
        await pilot.pause()
        assert app.commands[0].favorite is False
        assert app.commands[0].pinned is True
        assert len(saved) == 2


@pytest.mark.tui
@pytest.mark.asyncio
async def test_delete_preset_requires_confirmation(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    monkeypatch.setattr("ambrosia.tui.app.remove_command", lambda _id: None)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert type(app.screen).__name__ == "_ConfirmModal"
        app.query_one("#cancel", Button).press()
        await pilot.pause()
        assert len(app.commands) == 2
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        app.query_one("#confirm", Button).press()
        await pilot.pause()
        assert len(app.commands) == 1


@pytest.mark.tui
@pytest.mark.asyncio
async def test_export_presets_writes_requested_path(tmp_path: Path) -> None:
    app = _app()
    target = tmp_path / "export.json"
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_export_presets()
        await pilot.pause()
        app.query_one("#input-path", Input).value = str(target)
        app.query_one("#submit", Button).press()
        await pilot.pause()
        assert target.exists()
        assert len(json.loads(target.read_text())) == 2


@pytest.mark.tui
@pytest.mark.asyncio
async def test_import_presets_merges(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "import.json"
    source.write_text(
        json.dumps([{"id": "new", "name": "New", "description": "", "shell": "true"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr("ambrosia.tui.app.save_commands", lambda _commands: None)
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_import_presets()
        await pilot.pause()
        app.query_one("#input-path", Input).value = str(source)
        app.query_one("#submit", Button).press()
        await pilot.pause()
        assert any(command.id == "new" for command in app.commands)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_empty_path_import_and_export_are_rejected() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_import_presets()
        await pilot.pause()
        app.query_one("#input-path", Input).value = ""
        app.query_one("#submit", Button).press()
        await pilot.pause()
        assert len(app.commands) == 2
        assert len(app.screen_stack) == 1


@pytest.mark.tui
@pytest.mark.asyncio
async def test_save_session_is_notification_only() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_save_session()
        await pilot.pause()
        assert app._session_values == {}


@pytest.mark.tui
@pytest.mark.asyncio
async def test_toggle_history_and_scope(monkeypatch: MonkeyPatch) -> None:
    saved: list[ScopePolicy] = []
    monkeypatch.setattr("ambrosia.tui.app.load_scope_policy", lambda: ScopePolicy())
    monkeypatch.setattr("ambrosia.tui.app.save_scope_policy", saved.append)
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        initial_history = app.history_store.enabled
        app.action_toggle_history()
        assert app.history_store.enabled is not initial_history
        app.action_toggle_scope()
        assert app.scope_policy is not None and app.scope_policy.enabled is True
        assert saved == [app.scope_policy]
        app.action_toggle_scope()
        assert app.scope_policy is not None and app.scope_policy.enabled is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_quit_wipes_in_memory_and_persisted_session(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    session_file = tmp_path / "session.json"
    session_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("ambrosia.tui.app.SESSION_FILE", session_file)

    class _Store:
        def __init__(self) -> None:
            self.names = ["a", "b"]
            self.deleted: list[str] = []

        def list_sessions(self) -> list[str]:
            return list(self.names)

        def delete_session(self, name: str) -> None:
            self.deleted.append(name)

    store = _Store()
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app._session_values["target"] = "10.0.0.1"
        app.session_store = store  # type: ignore[assignment]
        app.action_quit_app()
        await pilot.pause()
        assert app.is_running is False
        assert app._session_values == {}
        assert session_file.exists() is False
        assert store.deleted == ["a", "b"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_quit_with_running_job_asks_confirmation() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.running = True
        app.action_quit_app()
        await pilot.pause()
        assert type(app.screen).__name__ == "_ConfirmModal"
        app.query_one("#cancel", Button).press()
        await pilot.pause()
        assert app.is_running is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_quick_run_with_missing_inputs_opens_form() -> None:
    command = Command(
        id="c",
        name="secure",
        description="",
        shell="tool {{target}}",
        inputs=[CommandInput(id="target", prompt="Target", required=True)],
    )
    app = _app(commands=[command])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert type(app.screen).__name__ == "InputFormModal"
        assert app.execution_visible is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_copy_command_uses_shared_session_values(monkeypatch: MonkeyPatch) -> None:
    command = Command(
        id="c",
        name="copy",
        description="",
        shell="nmap {{target}}",
        inputs=[CommandInput(id="target", prompt="Target")],
    )
    app = _app(commands=[command])
    copied: list[str] = []
    monkeypatch.setattr(app, "_copy_to_clipboard", lambda text: copied.append(text) or True)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app._remember_values(command, {"target": "10.0.0.9"})
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert copied == ["nmap 10.0.0.9"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_copy_command_uses_uppercase_names_for_unset_inputs(monkeypatch: MonkeyPatch) -> None:
    command = Command(
        id="c2",
        name="copy unset",
        description="",
        shell="nmap -sV {{target}} {{ports}}",
        inputs=[
            CommandInput(id="target", prompt="Target"),
            CommandInput(id="ports", prompt="Ports"),
        ],
    )
    app = _app(commands=[command])
    copied: list[str] = []
    monkeypatch.setattr(app, "_copy_to_clipboard", lambda text: copied.append(text) or True)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert copied == ["nmap -sV TARGET PORTS"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_run_again_starts_last_command() -> None:
    command = Command(id="c", name="echo", description="", shell="printf again", inputs=[])
    app = _app(commands=[command])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app._last_command = command
        app._last_values = {"unused": "1"}
        app.action_run_again()
        await asyncio.sleep(0.3)
        await pilot.pause()
        assert app.execution_visible is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_scope_policy_blocks_run() -> None:
    command = Command(
        id="c",
        name="scan",
        description="",
        shell="nmap {{target}}",
        inputs=[CommandInput(id="target", prompt="Target")],
    )
    app = _app(commands=[command])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.scope_policy = ScopePolicy(enabled=True, mode="denylist", exclude_cidrs=["10.0.0.0/8"])
        await app._run_command(command, {"target": "10.0.0.5"})
        assert app.execution_visible is False
        assert app.running is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_escape_clears_filters_in_order() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.query_one("#search-bar", Input).value = "nmap"
        app.active_tags = ["nmap"]
        app.library_view = "pinned"
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.search_query == ""
        await pilot.press("escape")
        await pilot.pause()
        assert app.active_tags == []
        await pilot.press("escape")
        await pilot.pause()
        assert app.library_view == "all"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_r_key_cycles_mode_with_explorer_focus() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert app.search_mode == "fuzzy"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_get_css_variables_uses_warm_palette() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        variables = app.get_css_variables()
        assert variables["primary"].lower() == AMBER.lower()
        assert variables["secondary"].lower() == FEMME_PINK.lower()
        assert variables["accent"].lower() == PHOSPHOR.lower()
        assert variables["background"].lower() == DEEP_PANEL_BG.lower()


@pytest.mark.tui
@pytest.mark.asyncio
async def test_session_file_constant_is_memory_only_path() -> None:
    assert SESSION_FILE.name == "session.json"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_missing_preset_command_notifies() -> None:
    workflow = Workflow(name="W", id="w", phases={"p": ["absent"]})
    app = _app(commands=[], workflows=[workflow])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await _open_workflow(pilot, app)
        await pilot.press("enter")
        await pilot.pause()
        assert app.execution_visible is False
        assert app.workflow_visible is True


async def _open_workflow(pilot: object, app: AmbrosiaApp) -> None:
    app.query_one("#search-bar", Input).value = "t:w"
    await _settled(pilot)
    app.action_focus_explorer()
    await pilot.pause()  # type: ignore[attr-defined]
    await pilot.press("enter")  # type: ignore[attr-defined]
    await asyncio.sleep(0.15)
    await pilot.pause()  # type: ignore[attr-defined]
    await pilot.pause()  # type: ignore[attr-defined]


# ============================================================ validation branches


def test_add_preset_rejects_missing_required_fields() -> None:
    app = _app()
    before = list(app.commands)
    app._handle_add_preset({"id": "", "name": "x", "shell": "true"})
    app._handle_add_preset({"id": "x", "name": "", "shell": "true"})
    app._handle_add_preset({"id": "x", "name": "x", "shell": ""})
    app._handle_add_preset(None)
    assert app.commands == before


def test_add_preset_reports_duplicate_id(monkeypatch: MonkeyPatch) -> None:
    def _raise(_command: Command) -> None:
        msg = "command id already exists: 'c1'"
        raise ValueError(msg)

    monkeypatch.setattr("ambrosia.tui.app.add_command", _raise)
    app = _app()
    before = list(app.commands)
    app._handle_add_preset({"id": "c1", "name": "again", "shell": "true"})
    assert app.commands == before


def test_edit_preset_rejects_missing_fields(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    original = _commands()[0]
    saved: list[list[Command]] = []
    monkeypatch.setattr("ambrosia.tui.app.save_commands", saved.append)
    app._handle_edit_preset({"id": "", "name": "x", "shell": "true"}, original)
    app._handle_edit_preset(None, original)
    assert saved == []


@pytest.mark.tui
@pytest.mark.asyncio
async def test_export_empty_path_is_rejected(tmp_path: Path) -> None:
    app = _app()
    target = tmp_path / "must-not-exist.json"
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_export_presets()
        await pilot.pause()
        app.query_one("#input-path", Input).value = ""
        app.query_one("#submit", Button).press()
        await pilot.pause()
        assert target.exists() is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_import_invalid_json_keeps_catalog(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text("not json", encoding="utf-8")
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_import_presets()
        await pilot.pause()
        app.query_one("#input-path", Input).value = str(source)
        app.query_one("#submit", Button).press()
        await pilot.pause()
        assert [command.id for command in app.commands] == ["c1", "c2"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_quit_confirm_yes_exits() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.running = True
        app.action_quit_app()
        await pilot.pause()
        app.query_one("#confirm", Button).press()
        await pilot.pause()
        assert app.is_running is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_cancel_job_marks_execution_cancelled(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    monkeypatch.setattr(app.executor, "cancel", lambda: None)
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.running = True
        app.action_cancel_job()
        await pilot.pause()
        assert "cancelled" in str(app.query_one("#execution-status", Static).renderable)


@pytest.mark.tui
@pytest.mark.asyncio
async def test_select_from_search_focuses_explorer() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await app.action_select()
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "preset-explorer"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_select_with_no_results_is_safe() -> None:
    app = _app(commands=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.screen_stack) == 1
        assert app.execution_visible is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_search_mode_and_quick_run_guarded_during_execution() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.execution_visible = True
        await pilot.pause()
        mode = app.search_mode
        app.action_cycle_search_mode()
        app.action_quick_run()
        await pilot.pause()
        assert app.search_mode == mode
        assert len(app.screen_stack) == 1


@pytest.mark.tui
@pytest.mark.asyncio
async def test_crud_actions_guarded_during_execution() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.execution_visible = True
        await pilot.pause()
        for action in (
            app.action_add_preset,
            app.action_edit_preset,
            app.action_delete_preset,
            app.action_export_presets,
            app.action_import_presets,
        ):
            action()
            await pilot.pause()
        assert len(app.screen_stack) == 1


@pytest.mark.tui
@pytest.mark.asyncio
async def test_copy_or_cancel_cancels_running_job(monkeypatch: MonkeyPatch) -> None:
    app = _app()
    calls: list[int] = []
    monkeypatch.setattr(app, "action_cancel_job", lambda: calls.append(1))
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.execution_visible = True
        app.running = True
        app.action_copy_or_cancel()
        await pilot.pause()
        assert calls == [1]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_focus_next_wraps_to_search_without_selection() -> None:
    app = _app(commands=[])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.action_focus_explorer()
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "search-bar"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_tag_browser_set_mode_helper() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        browser = app.query_one("#tag-browser", TagBrowser)
        browser.set_mode("and")
        assert browser._mode == "and"
        browser._tag_checkboxes["nmap"].value = True
        await pilot.pause()
        assert app.tag_mode == "and"


@pytest.mark.tui
@pytest.mark.asyncio
async def test_session_change_marks_dirty() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app._session_dirty = False
        app._on_session_changed()
        assert app._session_dirty is True


@pytest.mark.tui
@pytest.mark.asyncio
async def test_footer_refresh_is_safe_before_compose() -> None:
    app = _app()
    app._refresh_footer()  # must not raise before widgets are mounted


@pytest.mark.tui
@pytest.mark.asyncio
async def test_inspector_run_request_guarded_during_execution() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.execution_visible = True
        await pilot.pause()
        app.query_one("#configure-run", Button).press()
        await pilot.pause()
        assert app.running is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_activation_guarded_during_execution() -> None:
    workflow = _workflows()[0]
    app = _app(commands=[], workflows=[workflow])
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        app.execution_visible = True
        await pilot.pause()
        await app.action_open_workflow(workflow)
        assert app.workflow_visible is False
        assert app.active_workflow is None


@pytest.mark.tui
@pytest.mark.asyncio
async def test_workflow_phase_actions_guarded_when_runner_closed() -> None:
    app = _app()
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        await app.action_workflow_next_phase()
        await app.action_workflow_prev_phase()
        assert app.workflow_phase_index == 0
        assert app.workflow_visible is False
