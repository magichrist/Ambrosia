# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Tests for workflows and their integration with TUI search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ambrosia.model import Command
from ambrosia.tui.matching import (
    parse_search_query,
    regex_error,
    search_items,
    search_workflows,
)
from ambrosia.workflow import Workflow, load_workflow_file, load_workflows_from_dir

if TYPE_CHECKING:
    from pathlib import Path


def _workflow() -> Workflow:
    return Workflow(
        name="Linux Recon",
        id="linux-recon",
        description="Read-only Linux reconnaissance chain.",
        phases={
            "discovery": ["linux.nmap.discovery", "linux.ssh.version"],
            "exposure": ["windows.rdp.exposure"],
        },
    )


def test_workflow_helpers() -> None:
    workflow = _workflow()
    assert workflow.phase_names() == ["discovery", "exposure"]
    assert workflow.command_ids() == [
        "linux.nmap.discovery",
        "linux.ssh.version",
        "windows.rdp.exposure",
    ]
    assert workflow.command_ids("discovery") == ["linux.nmap.discovery", "linux.ssh.version"]
    assert workflow.command_count() == 3


def test_load_workflow_file_uses_stem_as_id(tmp_path: Path) -> None:
    path = tmp_path / "linux-recon.workflow"
    path.write_text(
        "name: Linux Recon\ndescription: read-only chain\nphases:\n"
        "  discovery:\n    - linux.nmap.discovery\n",
        encoding="utf-8",
    )
    workflow = load_workflow_file(path)
    assert workflow is not None
    assert workflow.id == "linux-recon"
    assert workflow.description == "read-only chain"
    assert load_workflows_from_dir(tmp_path) == [workflow]


def test_type_qualifier_is_parsed_and_not_regex_validated() -> None:
    query = parse_search_query("type:workflow linux", "regex")
    assert query.qualifiers == {"type": "workflow"}
    assert query.free_text == "linux"
    assert regex_error(query) is None


def test_short_type_qualifier_aliases() -> None:
    for raw in ("t:w", "t:workflow", "type:w", "t:W"):
        query = parse_search_query(raw)
        assert query.qualifiers == {"type": "workflow"}, raw
    assert parse_search_query("t:p").qualifiers == {"type": "preset"}
    assert parse_search_query("t:a").qualifiers == {"type": "all"}
    # Free text still works alongside the shorthand.
    mixed = parse_search_query("t:w linux")
    assert mixed.qualifiers == {"type": "workflow"}
    assert mixed.free_text == "linux"


def test_t_w_search_returns_only_workflows() -> None:
    command = Command(
        id="linux.nmap.discovery", name="nmap", description="", shell="nmap {{target}}"
    )
    results = search_items([command], [_workflow()], parse_search_query("t:w"))
    assert len(results) == 1
    assert results[0].workflow is not None


def test_type_workflow_returns_only_workflows() -> None:
    command = Command(
        id="linux.nmap.discovery", name="nmap", description="", shell="nmap {{target}}"
    )
    results = search_items([command], [_workflow()], parse_search_query("type:workflow"))
    assert len(results) == 1
    assert results[0].workflow is not None
    assert results[0].command is None


def test_type_preset_returns_only_presets() -> None:
    command = Command(
        id="linux.nmap.discovery", name="nmap", description="", shell="nmap {{target}}"
    )
    results = search_items([command], [_workflow()], parse_search_query("type:preset"))
    assert len(results) == 1
    assert results[0].command is command
    assert results[0].workflow is None


def test_type_all_returns_both_kinds() -> None:
    command = Command(
        id="linux.nmap.discovery", name="nmap", description="", shell="nmap {{target}}"
    )
    results = search_items([command], [_workflow()], parse_search_query("type:all"))
    assert {type(result.item) for result in results} == {Command, Workflow}


def test_workflow_matches_name_description_and_command_ids() -> None:
    workflow = _workflow()
    for raw in ("recon", "read-only", "linux-recon", "discovery", "cmd:rdp"):
        assert search_workflows([workflow], parse_search_query(raw)), raw
    assert search_workflows([workflow], parse_search_query("windows tree")) == []
