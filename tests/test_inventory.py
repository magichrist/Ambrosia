# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Integrity checks for the shipped preset and workflow inventory."""

from __future__ import annotations

from pathlib import Path

from ambrosia.storage import load_preset_file, load_presets_from_dir
from ambrosia.tui.matching import parse_search_query, search_commands
from ambrosia.workflow import load_workflows_from_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESETS_DIR = REPO_ROOT / "inventory" / "presets"
WORKFLOWS_DIR = REPO_ROOT / "inventory" / "workflow"


def test_every_preset_file_loads() -> None:
    files = sorted(PRESETS_DIR.rglob("*.preset"))
    assert files, "expected shipped presets"
    for path in files:
        assert load_preset_file(path), f"preset failed to load: {path}"


def test_preset_ids_are_unique_and_os_prefixed() -> None:
    commands = load_presets_from_dir(PRESETS_DIR)
    ids = [command.id for command in commands]
    assert len(ids) == len(set(ids)), "duplicate preset ids"
    for command in commands:
        os_dir = command.id.split(".", 1)[0]
        assert os_dir in {"linux", "windows"}, command.id
        assert command.id.startswith(f"{os_dir}."), command.id
        assert command.category == os_dir, command.id


def test_multi_term_search_finds_shipped_preset() -> None:
    commands = load_presets_from_dir(PRESETS_DIR)
    results = search_commands(commands, parse_search_query("regis rdp"))
    assert any(result.item.id == "windows.reg-disable-nla" for result in results)


def test_every_workflow_reference_resolves() -> None:
    command_ids = {command.id for command in load_presets_from_dir(PRESETS_DIR)}
    workflows = load_workflows_from_dir(WORKFLOWS_DIR)
    assert workflows, "expected shipped workflows"
    for workflow in workflows:
        references = workflow.command_ids()
        assert references, f"empty workflow: {workflow.id}"
        missing = [ref for ref in references if ref not in command_ids]
        assert not missing, f"{workflow.id}: unknown preset ids {missing}"
