# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Tests for JSON command persistence: load, save, add, remove.

Uses :func:`pytest.tmp_path` so no real files on disk are touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambrosia.model import Command, CommandInput
from ambrosia.storage import add_command, load_commands, remove_command, save_commands


def _cmd(cmd_id: str, name: str, shell: str) -> Command:
    return Command(
        id=cmd_id,
        name=name,
        description=f"{name} description",
        shell=shell,
        tags=[name.split()[0]],
        inputs=[CommandInput(id="target", prompt="Target", required=True)],
    )


def test_save_and_load_round_trip(tmp_path) -> None:
    path = tmp_path / "commands.json"
    commands = [
        _cmd("c1", "nmap scan", "nmap -sV {{target}}"),
        _cmd("c2", "whois lookup", "whois {{target}}"),
    ]
    save_commands(commands, path)
    loaded = load_commands(path)
    assert len(loaded) == 2
    assert loaded[0] == commands[0]
    assert loaded[0].shell == "nmap -sV {{target}}"
    assert loaded[0].inputs[0].id == "target"
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    assert raw[0]["id"] == "c1"
    assert raw[0]["shell"] == "nmap -sV {{target}}"


def test_load_missing_file_returns_empty(tmp_path) -> None:
    assert load_commands(tmp_path / "nonexistent.json") == []


def test_add_command_duplicate_id_raises(tmp_path) -> None:
    path = tmp_path / "commands.json"
    cmd = _cmd("c1", "one", "one {{target}}")
    add_command(cmd, path)
    with pytest.raises(ValueError, match="command id already exists"):
        add_command(cmd, path)


def test_remove_command(tmp_path) -> None:
    path = tmp_path / "commands.json"
    add_command(_cmd("c1", "one", "one {{target}}"), path)
    add_command(_cmd("c2", "two", "two {{target}}"), path)
    remove_command("c1", path)
    assert [c.id for c in load_commands(path)] == ["c2"]
    # Removing a missing id is idempotent and does not raise.
    remove_command("missing", path)
    assert [c.id for c in load_commands(path)] == ["c2"]
    remove_command("c2", path)
    assert load_commands(path) == []
