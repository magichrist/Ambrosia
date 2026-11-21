"""JSON persistence for v2 commands.

Commands are stored as a JSON list in ``~/.ambrosia/commands.json`` by default.
Writes are atomic (temp file in the same directory then
:meth:`pathlib.Path.replace`) and the parent directory is created as needed.
Reads degrade gracefully: a missing, empty, or corrupt file yields an empty
catalog.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from ambrosia.model import Command

COMMANDS_FILE = Path.home() / ".ambrosia" / "commands.json"


def load_commands(path: Path = COMMANDS_FILE) -> list[Command]:
    """Load commands from ``path``.

    Returns an empty list if the file is missing, empty, or contains invalid
    JSON, or if the top-level JSON value is not a list. Non-object items in
    the list are skipped.
    """
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    commands: list[Command] = []
    for item in data:
        if isinstance(item, dict):
            commands.append(Command.from_dict(item))
    return commands


def save_commands(commands: list[Command], path: Path = COMMANDS_FILE) -> None:
    """Atomically write ``commands`` to ``path`` as JSON.

    Parent directories are created as needed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [command.to_dict() for command in commands]
    text = json.dumps(payload, indent=2, allow_nan=False, ensure_ascii=False) + "\n"
    _atomic_write_text(path, text)


def load_preset_file(path: Path) -> list[Command]:
    """Load commands from a ``.preset`` file.

    A ``.preset`` file is YAML containing either a single command object or a
    JSON/YAML list of command objects. The ``id`` is derived from the file
    stem (e.g. ``smb.audit.preset`` -> ``smb.audit``) and is not required in
    the file itself. Returns an empty list if the file is missing or contains
    invalid YAML.
    """
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return []
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return []
    commands: list[Command] = []
    items: list[dict[str, object]] = []
    if isinstance(data, dict):
        items.append(data)
    elif isinstance(data, list):
        items = [item for item in data if isinstance(item, dict)]
    for item in items:
        item["id"] = path.stem
        commands.append(Command.from_dict(item))
    return commands


def load_presets_from_dir(directory: Path) -> list[Command]:
    """Load all ``.preset`` files from ``directory`` recursively.

    Walks subdirectories (e.g. ``inventory/presets/windows/``,
    ``inventory/presets/linux/``) so presets can be organized by OS or
    category. Files are returned in sorted path order for deterministic
    loading.
    """
    if not directory.exists() or not directory.is_dir():
        return []
    commands: list[Command] = []
    for preset_file in sorted(directory.rglob("*.preset")):
        commands.extend(load_preset_file(preset_file))
    return commands


def export_commands(commands: list[Command], path: Path) -> None:
    """Atomically write ``commands`` to ``path`` as JSON.

    Same atomic-write pattern as :func:`save_commands`; the target path is
    required because it names an export destination chosen by the user rather
    than the default catalog.
    """
    save_commands(commands, path)


def add_command(command: Command, path: Path = COMMANDS_FILE) -> None:
    """Append ``command`` to the catalog at ``path``.

    Raises :exc:`ValueError` if a command with the same id already exists.
    """
    existing = load_commands(path)
    for current in existing:
        if current.id == command.id:
            msg = f"command id already exists: {command.id!r}"
            raise ValueError(msg)
    existing.append(command)
    save_commands(existing, path)


def remove_command(command_id: str, path: Path = COMMANDS_FILE) -> None:
    """Remove the command with ``command_id`` from the catalog at ``path``.

    It is not an error if no command with that id exists.
    """
    existing = load_commands(path)
    filtered = [current for current in existing if current.id != command_id]
    save_commands(filtered, path)


def get_categories(commands: list[Command]) -> list[str]:
    """Return sorted unique categories from ``commands`` (excluding empty)."""
    return sorted({command.category for command in commands if command.category})


def get_favorites(commands: list[Command]) -> list[Command]:
    """Return commands where ``favorite`` is True, preserving input order."""
    return [command for command in commands if command.favorite]


def get_pinned(commands: list[Command]) -> list[Command]:
    """Return commands where ``pinned`` is True, preserving input order."""
    return [command for command in commands if command.pinned]


def import_commands(path: Path, *, merge: bool = False) -> list[Command]:
    """Read commands from ``path`` and return the resulting catalog.

    If ``merge`` is False (default), the imported commands replace the
    catalog entirely. If True, they are appended to the existing catalog at
    :data:`COMMANDS_FILE`, skipping any command whose id already exists there.

    Raises :exc:`ValueError` if ``path`` is missing or empty, contains invalid
    JSON, its top-level value is not a list, any item is not a command object
    or lacks a required field (``id``, ``name``, ``shell``), or merging would
    introduce a duplicate id.
    """
    if not path.exists():
        msg = f"commands file not found: {path}"
        raise ValueError(msg)
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        msg = f"commands file is empty: {path}"
        raise ValueError(msg)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"invalid JSON in {path}: {exc}"
        raise ValueError(msg) from exc
    if not isinstance(data, list):
        msg = f"expected a JSON list of commands in {path}"
        raise ValueError(msg)  # noqa: TRY004 -- spec requires ValueError for invalid import files

    imported: list[Command] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            msg = f"item {index} in {path} is not a command object"
            raise ValueError(msg)  # noqa: TRY004 -- spec requires ValueError for invalid import files
        _validate_command_item(item, path, index)
        command = Command.from_dict(item)
        if command.id in seen_ids:
            msg = f"duplicate command id {command.id!r} in {path}"
            raise ValueError(msg)
        seen_ids.add(command.id)
        imported.append(command)

    if not merge:
        return imported

    existing = load_commands(COMMANDS_FILE)
    existing_ids = {command.id for command in existing}
    for command in imported:
        if command.id not in existing_ids:
            existing.append(command)
    return existing


def _validate_command_item(item: dict[str, object], path: Path, index: int) -> None:
    """Require ``id``, ``name`` and ``shell`` on a deserialized command item."""
    for field_name in ("id", "name", "shell"):
        value = item.get(field_name)
        if not isinstance(value, str) or not value.strip():
            msg = f"item {index} in {path} is missing required field {field_name!r}"
            raise ValueError(msg)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically via a temp file in the same dir."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_file.write(text)
        temp_path = Path(temp_file.name)
    try:
        temp_path.replace(path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    """Self-test: round-trip a sample command through JSON storage."""
    import tempfile as _tempfile  # noqa: PLC0415

    from ambrosia.model import Command, CommandInput

    cmd = Command(  # noqa: S604 -- ``shell`` is a template, not executed by a shell
        id="smb-version",
        name="windows version check smb",
        description="uses crackmapexec smb to get windows version",
        tags=["smb", "windows", "crackmapexec", "windows version"],
        shell="crackmapexec smb {{ip}}",  # noqa: S604 -- template, not shell=True
        category="recon",
        favorite=True,
        pinned=False,
        inputs=[
            CommandInput(
                id="ip",
                prompt="Target IP or hostname",
                type="host",
                required=True,
                secret=False,
                validation_hint="IPv4 address or hostname",
            )
        ],
    )

    # Model methods.
    assert cmd.input_by_id("ip") is not None  # noqa: S101
    assert cmd.input_by_id("nope") is None  # noqa: S101
    assert len(cmd.required_inputs()) == 1  # noqa: S101
    assert cmd.all_inputs_filled({"ip": "10.0.0.1"})  # noqa: S101
    assert not cmd.all_inputs_filled({})  # noqa: S101
    assert not cmd.all_inputs_filled({"ip": ""})  # noqa: S101

    with _tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "commands.json"

        # Missing file -> [].
        assert load_commands(path) == []  # noqa: S101

        # Save + load round-trip.
        save_commands([cmd], path)
        loaded = load_commands(path)
        assert loaded == [cmd]  # noqa: S101

        # New v2 fields round-trip through JSON storage.
        assert loaded[0].category == "recon"  # noqa: S101
        assert loaded[0].favorite is True  # noqa: S101
        assert loaded[0].pinned is False  # noqa: S101
        assert loaded[0].inputs[0].validation_hint == "IPv4 address or hostname"  # noqa: S101

        # Duplicate id -> ValueError.
        try:
            add_command(cmd, path)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for duplicate id")

        # Add a second command, then remove it.
        cmd2 = Command(  # noqa: S604 -- ``shell`` is a template, not executed by a shell
            id="kerberoast",
            name="ad kerberoast",
            description="request service tickets for offline cracking",
            tags=["ad", "kerberos"],
            shell="GetUserSPNs.py -dc-ip {{dc}} {{domain}}/{{user}}:{{password}} -request",  # noqa: S604
            inputs=[
                CommandInput(id="dc", prompt="Domain controller IP", type="host"),
                CommandInput(
                    id="password",
                    prompt="Password",
                    type="string",
                    secret=True,
                ),
            ],
        )
        add_command(cmd2, path)
        assert len(load_commands(path)) == 2  # noqa: S101
        remove_command("kerberoast", path)
        assert len(load_commands(path)) == 1  # noqa: S101
        # Idempotent remove of a missing id.
        remove_command("does-not-exist", path)
        assert len(load_commands(path)) == 1  # noqa: S101

        # Phase 3 ergonomics helpers.
        catalog = load_commands(path)
        cmd3 = Command(  # noqa: S604 -- ``shell`` is a template, not executed by a shell
            id="mimikatz",
            name="mimikatz logonpasswords",
            description="dump logon passwords via mimikatz",
            tags=["mimikatz", "credentials"],
            shell='mimikatz.exe "privilege::debug" "logonpasswords" "exit"',  # noqa: S604
            category="exploit",
            favorite=False,
            pinned=True,
        )
        all_cmds = [cmd, cmd2, cmd3]
        assert get_categories(all_cmds) == ["exploit", "recon"]  # noqa: S101
        assert get_favorites(all_cmds) == [cmd]  # noqa: S101
        assert get_pinned(all_cmds) == [cmd3]  # noqa: S101
        assert get_categories([]) == []  # noqa: S101
        assert get_favorites(catalog) == [cmd]  # noqa: S101

    print("v2 storage self-test: all checks passed")
