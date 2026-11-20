# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""TUI wiring tests: navigation, keybindings, buttons, and stale callbacks.

These use Textual's ``run_test`` harness against the demo service stack from
``ambrosia.tui.__main__`` (in-memory fakes, no subprocesses, no database). They
are regression tests for the wiring defects that previously made every
keybinding and button a no-op and crashed the app on startup.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from ambrosia.tui.app import AmbrosiaApp


def _build_demo_app() -> AmbrosiaApp:
    import ambrosia.tui.app as appmod

    captured: dict[str, AmbrosiaApp] = {}
    original_run = appmod.AmbrosiaApp.run

    def capture(self: AmbrosiaApp, *args: object, **kwargs: object) -> None:
        captured.setdefault("app", self)

    appmod.AmbrosiaApp.run = capture  # type: ignore[method-assign]
    try:
        module = importlib.import_module("ambrosia.tui.__main__")
        module.main()
    finally:
        appmod.AmbrosiaApp.run = original_run  # type: ignore[method-assign]
    return captured["app"]


@pytest.mark.tui
@pytest.mark.asyncio
async def test_app_mounts_and_all_keybindings_resolve() -> None:
    app = _build_demo_app()
    async with app.run_test(size=(200, 80)) as pilot:
        await pilot.pause()
        assert app.current_view() is not None

        for action in [
            "search",
            "focus_next",
            "open",
            "go_back",
            "engagement_switcher",
            "help",
            "refresh",
            "target_scope",
            "preset_browser",
            "job_monitor",
            "findings",
            "artifacts",
        ]:
            assert await app.run_action(action), f"action {action!r} did not resolve"
            if len(app.screen_stack) > 1:
                await pilot.press("escape")
            await pilot.pause()


@pytest.mark.tui
@pytest.mark.asyncio
async def test_all_views_mount_without_duplicate_ids() -> None:
    from ambrosia.tui.app import (
        VIEW_ARTIFACTS,
        VIEW_DASHBOARD,
        VIEW_ENGAGEMENTS,
        VIEW_FINDINGS,
        VIEW_JOBS,
        VIEW_PRESETS,
        VIEW_TARGET_SCOPE,
    )

    app = _build_demo_app()
    async with app.run_test(size=(200, 80)) as pilot:
        await pilot.pause()
        for name in [
            VIEW_ENGAGEMENTS,
            VIEW_DASHBOARD,
            VIEW_TARGET_SCOPE,
            VIEW_PRESETS,
            VIEW_JOBS,
            VIEW_ARTIFACTS,
            VIEW_FINDINGS,
            VIEW_DASHBOARD,
        ]:
            app.show_view(name)
            await pilot.pause()
            assert app.current_view() is not None, name

        # Rapid repeated navigation must not raise DuplicateIds.
        for _ in range(3):
            app.show_view(VIEW_ENGAGEMENTS)
            await pilot.pause()
            app.show_view(VIEW_DASHBOARD)
            await pilot.pause()


@pytest.mark.tui
@pytest.mark.asyncio
async def test_every_view_button_is_wired() -> None:
    from ambrosia.tui.app import (
        VIEW_ARTIFACTS,
        VIEW_ENGAGEMENTS,
        VIEW_FINDINGS,
        VIEW_JOBS,
        VIEW_PRESETS,
        VIEW_TARGET_SCOPE,
    )

    app = _build_demo_app()
    async with app.run_test(size=(200, 80)) as pilot:
        await pilot.pause()
        buttons = {
            VIEW_ENGAGEMENTS: ["refresh-engagements", "create-engagement"],
            VIEW_TARGET_SCOPE: ["refresh-scope", "add-target"],
            VIEW_PRESETS: [
                "refresh-presets",
                "validate-preset",
                "plan-preset",
                "save-preset",
                "back-presets",
            ],
            VIEW_JOBS: ["refresh-jobs", "cancel-job", "back-jobs"],
            VIEW_ARTIFACTS: ["refresh-artifacts", "back-artifacts"],
            VIEW_FINDINGS: ["refresh-findings", "back-findings"],
        }
        for name, ids in buttons.items():
            app.show_view(name)
            await pilot.pause()
            for button_id in ids:
                await pilot.click(f"#{button_id}")
                await pilot.pause()
            while len(app.screen_stack) > 1:
                await pilot.press("escape")
                await pilot.pause()


@pytest.mark.tui
@pytest.mark.asyncio
async def test_action_details_controls_work_and_escape_only_closes_modal() -> None:
    app = _build_demo_app()
    async with app.run_test(size=(200, 80)) as pilot:
        await pilot.pause()
        app.show_view("action_details", action_id="network.nmap.service_discovery")
        await pilot.pause()

        for button_id in ["typed-inputs", "dry-run-action"]:
            await pilot.click(f"#{button_id}")
            await pilot.pause()
            assert len(app.screen_stack) > 1, button_id
            await pilot.press("escape")
            await pilot.pause()
            # Escape closes the modal WITHOUT navigating away.
            assert len(app.screen_stack) == 1
            assert app.active_view == "action_details"

        await pilot.click("#run-action")
        await pilot.pause()
        await pilot.click("#back-action")
        await pilot.pause()
        assert app.active_view != "action_details"
