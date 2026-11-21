"""Minimal CLI for the Ambrosia v2 command launcher TUI.

The app has a single behaviour: launch the Textual TUI. Invoking it with no
arguments starts the TUI (commands and session are loaded from their default
files); ``--commands-file`` and ``--session-file`` override those defaults.
There are no subcommand groups.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from ambrosia.model import Command
    from ambrosia.workflow import Workflow

from ambrosia.storage import (
    COMMANDS_FILE,
    export_commands,
    import_commands,
    load_commands,
    load_preset_file,
    load_presets_from_dir,
    save_commands,
)
from ambrosia.tui.app import AmbrosiaApp
from ambrosia.workflow import load_workflow_file, load_workflows_from_dir

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
    preset_file: str | None = typer.Option(
        None,
        "--preset-file",
        help="Path to a .preset file to load commands from.",
    ),
    preset_dir: str | None = typer.Option(
        None,
        "--preset-dir",
        help="Directory of .preset files to load commands from (e.g. inventory/presets).",
    ),
    import_file: str | None = typer.Option(
        None,
        "--import-file",
        help="Import and merge commands from this JSON file into the default catalog before launching the TUI.",
    ),
    export_file: str | None = typer.Option(
        None,
        "--export-file",
        help="Export the default command catalog to this JSON path, then exit.",
    ),
) -> None:
    """Launch the Ambrosia v2 TUI.

    Session state is loaded from ~/.ambrosia/session.json by default; use the
    ``s`` binding inside the TUI to persist it.
    """
    commands: list[Command] | None = None
    if export_file is not None:
        commands = load_commands()
        export_commands(commands, Path(export_file))
        print(f"exported {len(commands)} commands to {export_file}")
        return

    if import_file is not None:
        commands = import_commands(Path(import_file), merge=True)
        save_commands(commands, COMMANDS_FILE)
        print(f"imported commands from {import_file} into {COMMANDS_FILE}")
    elif preset_dir is not None:
        commands = load_presets_from_dir(Path(preset_dir))
    elif preset_file is not None:
        commands = load_preset_file(Path(preset_file))
    elif commands_file is not None:
        commands = load_commands(Path(commands_file))
    AmbrosiaApp(commands=commands).run()


@app.command(name="workflow")
def workflow_cmd(
    workflow_file: str | None = typer.Option(
        None,
        "--workflow-file",
        help="Path to a .workflow file to display.",
    ),
    workflow_dir: str | None = typer.Option(
        None,
        "--workflow-dir",
        help="Directory of .workflow files to display (e.g. inventory/workflow).",
    ),
) -> None:
    """Display workflow definitions (phase-ordered command chains)."""
    if workflow_file is not None:
        wf = load_workflow_file(Path(workflow_file))
        if wf is None:
            print(f"workflow not found or invalid: {workflow_file}")
            raise typer.Exit(1)
        _print_workflow(wf)
        return

    if workflow_dir is not None:
        wfs = load_workflows_from_dir(Path(workflow_dir))
        if not wfs:
            print(f"no workflows found in {workflow_dir}")
            return
        for wf in wfs:
            _print_workflow(wf)
            print()
        return

    print("specify --workflow-file or --workflow-dir")
    raise typer.Exit(1)


def _print_workflow(wf: Workflow) -> None:
    """Pretty-print a single workflow."""
    print(f"Workflow: {wf.name}")
    for phase_name in wf.phase_names():
        ids = wf.command_ids(phase_name)
        print(f"  {phase_name}:")
        for cid in ids:
            print(f"    - {cid}")


def main() -> None:
    """Entry point for the ``ambrosia-v2`` console script.

    Invoking the typer app with no arguments launches the TUI directly; flags
    such as ``--commands-file`` and ``--session-file`` are parsed by typer.
    """
    app()


if __name__ == "__main__":
    main()
