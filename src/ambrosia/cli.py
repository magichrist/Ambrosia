"""Minimal CLI for the Ambrosia v2 command launcher TUI.

The app has a single behaviour: launch the Textual TUI. Invoking it with no
arguments starts the TUI (commands and session are loaded from their default
files); ``--commands-file`` and ``--session-file`` override those defaults.
There are no subcommand groups.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ambrosia.storage import load_commands
from ambrosia.tui.app import AmbrosiaApp

app = typer.Typer(
    name="ambrosia-v2",
    help="Ambrosia v2 — fast TUI-first command launcher.",
    rich_markup_mode="rich",
)


@app.command(name="tui")
def tui(
    commands_file: str | None = typer.Option(
        None, "--commands-file", help="Path to a JSON commands file to load."
    ),
) -> None:
    """Launch the Ambrosia v2 TUI.

    Session state is loaded from ~/.ambrosia/session.json by default; use the
    ``s`` binding inside the TUI to persist it.
    """
    commands = None
    if commands_file is not None:
        commands = load_commands(Path(commands_file))
    AmbrosiaApp(commands=commands).run()


def main() -> None:
    """Entry point for the ``ambrosia-v2`` console script.

    Invoking the typer app with no arguments launches the TUI directly; flags
    such as ``--commands-file`` and ``--session-file`` are parsed by typer.
    """
    app()


if __name__ == "__main__":
    main()
