# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Regression tests for the three-panel v2 TUI."""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Button, Input

from ambrosia.model import Command, CommandInput
from ambrosia.tui.app import AmbrosiaApp, _ConfirmRunModal
from ambrosia.tui.widgets.input_form import InputFormModal
from ambrosia.tui.widgets.preview import PresetInspector
from ambrosia.tui.widgets.results import PresetExplorer
from ambrosia.tui.widgets.tags import TagBrowser


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
    app = AmbrosiaApp(commands=_commands())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        assert app.query_one("#library").display is True
        assert app.query_one("#explorer").display is True
        assert app.query_one("#preset-inspector").display is True
        assert app.query_one("#execution-view").display is False
        assert app.execution_visible is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_sidebar_has_no_namespace_tree_and_populates_tags() -> None:
    app = AmbrosiaApp(commands=_commands())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        assert not app.query("#namespace-browser")
        tag_browser = app.query_one("#tag-browser", TagBrowser)
        assert list(tag_browser._tag_checkboxes) == ["linux", "nmap", "whois", "windows"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_first_result_selected_and_inspector_populated() -> None:
    app = AmbrosiaApp(commands=_commands())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        explorer = app.query_one("#preset-explorer", PresetExplorer)
        assert explorer.index == 0
        assert app.selected_command is not None
        assert app.selected_command.id == "c1"
        inspector = app.query_one("#preset-inspector", PresetInspector)
        assert "nmap scan" in str(inspector._content.renderable)
        assert inspector._run_button.disabled is False


@pytest.mark.tui
@pytest.mark.asyncio
async def test_result_rows_are_name_description_with_tooltip() -> None:
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=commands)
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=commands)
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
    commands = [
        Command(id="c1", name="echo", description="print", shell="printf hello", inputs=[])
    ]
    app = AmbrosiaApp(commands=commands)
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
    app = AmbrosiaApp(commands=_commands())
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
    app = AmbrosiaApp(commands=_commands())
    async with app.run_test(size=(140, 45)) as pilot:
        await _settled(pilot)
        assert app.focused is not None and app.focused.id == "search-bar"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "preset-explorer"
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "configure-run"
