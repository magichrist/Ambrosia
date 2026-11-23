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


def _relative_to_presets(path: Path) -> Path:
    """Return the path below the nearest ``presets`` directory, or just its name."""
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "presets":
            return Path(*parts[index + 1 :])
    return Path(path.name)


def _preset_identity(path: Path, root: Path | None = None) -> tuple[str, str]:
    """Derive ``(id, category)`` from a preset file's location.

    The id is the dot-joined relative path without ``.preset``, so
    ``inventory/presets/linux/http-get.preset`` becomes ``linux.http-get``.
    The category is the first segment (``linux``). With no ``root``, the path
    after a ``presets`` directory is used; files outside a presets tree keep
    the old stem-only behaviour.
    """
    if root is None:
        relative = _relative_to_presets(path)
    else:
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            relative = Path(path.name)
    parts = relative.with_suffix("").parts
    return ".".join(parts), parts[0] if len(parts) > 1 else ""


def load_preset_file(path: Path, *, root: Path | None = None) -> list[Command]:
    """Load commands from a ``.preset`` file.

    A ``.preset`` file is YAML containing either a single command object or a
    JSON/YAML list of command objects. The ``id`` and ``category`` are derived
    from the path (e.g. ``presets/linux/http-get.preset`` -> id
    ``linux.http-get``, category ``linux``); an ``id`` inside the file is
    ignored. ``root`` overrides the base used to derive them. Returns an empty
    list if the file is missing or contains invalid YAML.
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
    command_id, category = _preset_identity(path, root)
    for item in items:
        item["id"] = command_id
        item.setdefault("category", category)
        commands.append(Command.from_dict(item))
    return commands


def load_presets_from_dir(directory: Path) -> list[Command]:
    """Load all ``.preset`` files from ``directory`` recursively.

    Walks subdirectories (e.g. ``inventory/presets/windows/``,
    ``inventory/presets/linux/``) so presets can be organized by OS or
    category. Ids are derived from each file's path relative to ``directory``
    (e.g. ``linux/http-get.preset`` -> ``linux.http-get``), so identically
    named files in different folders stay distinct. Files are returned in
    sorted path order for deterministic loading. Duplicate ids are
    deduplicated (first occurrence wins).
    """
    if not directory.exists() or not directory.is_dir():
        return []
    commands: list[Command] = []
    seen_ids: set[str] = set()
    for preset_file in sorted(directory.rglob("*.preset")):
        for command in load_preset_file(preset_file, root=directory):
            if command.id not in seen_ids:
                seen_ids.add(command.id)
                commands.append(command)
    return commands


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
        for field_name in ("id", "name", "shell"):
            value = item.get(field_name)
            if not isinstance(value, str) or not value.strip():
                msg = f"item {index} in {path} is missing required field {field_name!r}"
                raise ValueError(msg)
        command = Command.from_dict(item)
        if command.id in seen_ids:
            msg = f"duplicate command id {command.id!r} in {path}"
            raise ValueError(msg)
        seen_ids.add(command.id)
        imported.append(command)

    if merge:
        existing = load_commands(COMMANDS_FILE)
        existing_ids = {command.id for command in existing}
        for command in imported:
            if command.id not in existing_ids:
                existing.append(command)
                existing_ids.add(command.id)
        return existing
    return imported


def get_categories(commands: list[Command]) -> list[str]:
    """Return sorted unique non-empty categories from commands."""
    return sorted({command.category for command in commands if command.category})


def get_all_tags(commands: list[Command]) -> dict[str, int]:
    """Return ``tag -> count`` for all tags used by ``commands``."""
    counts: dict[str, int] = {}
    for command in commands:
        for tag in command.tags:
            counts[tag] = counts.get(tag, 0) + 1
    return counts


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
        inputs=[
            CommandInput(
                id="ip",
                prompt="Target IP or hostname",
                type="host",
                required=True,
                secret=False,
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

    print("v2 storage self-test: all checks passed")
