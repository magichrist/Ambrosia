# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Tests for JSON command persistence: load, save, add, remove.

Uses :func:`pytest.tmp_path` so no real files on disk are touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ambrosia import storage
from ambrosia.model import Command, CommandInput
from ambrosia.storage import (
    add_command,
    export_commands,
    import_commands,
    load_commands,
    load_preset_file,
    load_presets_from_dir,
    remove_command,
    save_commands,
)


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


def test_export_commands_writes_json(tmp_path) -> None:
    path = tmp_path / "exported.json"
    commands = [_cmd("c1", "nmap scan", "nmap -sV {{target}}")]
    export_commands(commands, path)
    assert load_commands(path) == commands
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw[0]["id"] == "c1"


def test_import_commands_replaces_catalog(tmp_path) -> None:
    path = tmp_path / "import.json"
    save_commands([_cmd("c1", "one", "one {{t}}")], path)
    result = import_commands(path, merge=False)
    assert [c.id for c in result] == ["c1"]


def test_import_commands_merges_and_skips_duplicates(tmp_path, monkeypatch) -> None:
    catalog = tmp_path / "commands.json"
    monkeypatch.setattr(storage, "COMMANDS_FILE", catalog)
    save_commands([_cmd("existing", "existing", "existing {{t}}")], catalog)
    import_path = tmp_path / "import.json"
    save_commands(
        [
            _cmd("existing", "duplicate", "dup {{t}}"),
            _cmd("new", "new", "new {{t}}"),
        ],
        import_path,
    )
    result = import_commands(import_path, merge=True)
    assert [c.id for c in result] == ["existing", "new"]


def test_import_commands_merge_skips_ids_already_in_catalog(tmp_path, monkeypatch) -> None:
    catalog = tmp_path / "commands.json"
    monkeypatch.setattr(storage, "COMMANDS_FILE", catalog)
    save_commands([_cmd("c1", "one", "one {{t}}")], catalog)
    import_path = tmp_path / "import.json"
    save_commands([_cmd("c1", "one again", "one {{t}}")], import_path)
    result = import_commands(import_path, merge=True)
    assert [c.id for c in result] == ["c1"]


def test_import_commands_duplicate_ids_in_import_file_raise(tmp_path) -> None:
    import_path = tmp_path / "import.json"
    save_commands(
        [
            _cmd("c1", "one", "one {{t}}"),
            _cmd("c1", "one again", "one {{t}}"),
        ],
        import_path,
    )
    # Duplicate ids within the imported file are invalid whether or not we merge.
    for merge in (False, True):
        with pytest.raises(ValueError, match="duplicate command id"):
            import_commands(import_path, merge=merge)


def test_preset_id_and_category_come_from_path(tmp_path: Path) -> None:
    preset = tmp_path / "presets" / "linux" / "http-get.preset"
    preset.parent.mkdir(parents=True)
    preset.write_text(
        "name: HTTP GET\ndescription: Fetch a URL\ntags: [linux, http, curl, builtin]\n"
        'shell: "curl -sS {{url}}"\n',
        encoding="utf-8",
    )
    commands = load_preset_file(preset)
    assert [command.id for command in commands] == ["linux.http-get"]
    assert commands[0].category == "linux"
    assert commands[0].tags == ["linux", "http", "curl", "builtin"]


def test_presets_with_same_stem_in_different_folders_stay_distinct(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    for os_name in ("linux", "windows"):
        folder = root / os_name
        folder.mkdir(parents=True)
        (folder / "nmap.preset").write_text(
            f"name: Nmap {os_name}\ndescription: Nmap on {os_name}\n"
            f"tags: [{os_name}, nmap]\nshell: nmap {{target}}\n",
            encoding="utf-8",
        )
    commands = load_presets_from_dir(root)
    assert [command.id for command in commands] == ["linux.nmap", "windows.nmap"]
    assert [command.category for command in commands] == ["linux", "windows"]


def test_import_commands_invalid_file_raises(tmp_path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="not found"):
        import_commands(missing)

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        import_commands(bad_json)

    not_a_list = tmp_path / "not_a_list.json"
    not_a_list.write_text('{"id": "c1"}', encoding="utf-8")
    with pytest.raises(ValueError, match="expected a JSON list"):
        import_commands(not_a_list)

    missing_field = tmp_path / "missing_field.json"
    missing_field.write_text('[{"name": "n"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field"):
        import_commands(missing_field)
