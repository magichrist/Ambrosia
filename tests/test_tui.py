# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Smoke tests for the v2 TUI: mounting and search filtering."""

from __future__ import annotations

import pytest
from textual.widgets import Input, ListView

from ambrosia.model import Command
from ambrosia.tui.app import AmbrosiaApp


def _commands() -> list[Command]:
    return [
        Command(
            id="c1", name="nmap scan", description="d1", shell="nmap -sV {{target}}", inputs=[]
        ),
        Command(
            id="c2", name="whois lookup", description="d2", shell="whois {{target}}", inputs=[]
        ),
    ]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_app_mounts_and_lists_all_commands() -> None:
    app = AmbrosiaApp(commands=_commands())
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        results = app.query_one("#results", ListView)
        ids = [child.id for child in results.children]
        assert ids == ["c1", "c2"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_search_filters_results() -> None:
    app = AmbrosiaApp(commands=_commands())
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        results = app.query_one("#results", ListView)
        assert len(results.children) == 2

        search = app.query_one("#search-bar", Input)
        search.focus()
        for key in "nmap":
            await pilot.press(key)
        await pilot.pause()

        results = app.query_one("#results", ListView)
        ids = [child.id for child in results.children]
        assert ids == ["c1"]
