"""Minimal CLI for the Ambrosia v2 command launcher TUI.

Invoking ``ambrosia`` with no subcommand launches the TUI with defaults. The
``tui`` subcommand is still accepted for explicitness and exposes the loading
options; ``workflow`` prints phase-ordered workflow definitions.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer
from typer import Context

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
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def _default_to_tui(ctx: Context) -> None:
    """Launch the TUI when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        _launch_tui()


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
    workflow_dir: str | None = typer.Option(
        None,
        "--workflow-dir",
        help="Directory of .workflow files to load into the TUI (default: inventory/workflow).",
    ),
    workflow_file: str | None = typer.Option(
        None,
        "--workflow-file",
        help="Load a single .workflow file into the TUI.",
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
    """Launch the TUI (also the default when no subcommand is given)."""
    _launch_tui(
        commands_file=commands_file,
        preset_file=preset_file,
        preset_dir=preset_dir,
        workflow_dir=workflow_dir,
        workflow_file=workflow_file,
        import_file=import_file,
        export_file=export_file,
    )


def _launch_tui(
    commands_file: str | None = None,
    preset_file: str | None = None,
    preset_dir: str | None = None,
    workflow_dir: str | None = None,
    workflow_file: str | None = None,
    import_file: str | None = None,
    export_file: str | None = None,
) -> None:
    """Resolve the requested inputs and start the Textual app."""
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
    else:
        # Default: auto-load presets from inventory/presets/ if present,
        # otherwise fall back to the default commands catalog.
        default_preset_dir = Path("inventory/presets")
        if default_preset_dir.exists() and default_preset_dir.is_dir():
            commands = load_presets_from_dir(default_preset_dir)
        else:
            commands = load_commands()
    workflows: list[Workflow] | None = None
    if workflow_file is not None:
        loaded = load_workflow_file(Path(workflow_file))
        if loaded is None:
            print(f"workflow not found or invalid: {workflow_file}")
            raise typer.Exit(1)
        workflows = [loaded]
    elif workflow_dir is not None:
        workflows = load_workflows_from_dir(Path(workflow_dir))

    AmbrosiaApp(commands=commands, workflows=workflows).run()


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
    """Entry point for the ``ambrosia`` console script.

    With no subcommand this launches the TUI; use ``ambrosia workflow`` to print
    workflow definitions or ``ambrosia --help`` for the command list.
    """
    app()


if __name__ == "__main__":
    main()
