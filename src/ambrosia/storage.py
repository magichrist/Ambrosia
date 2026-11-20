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
