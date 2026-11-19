"""Ambrosia CLI entry point (Typer).

The CLI is a thin presentation layer. All business behavior lives in
application services (``ambrosia.application``), shared with the Textual TUI.
Commands never reach directly into repositories or launch subprocesses.
"""

from __future__ import annotations

import typer

from ambrosia.cli import commands  # noqa: F401  (registers command groups)

app = typer.Typer(
    name="ambrosia",
    help="Ambrosia — context-driven automation workbench for authorized assessment.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Register command-group sub-apps (kept thin; application services own logic).
app.add_typer(commands.engagement_app, name="engagement")
app.add_typer(commands.scope_app, name="scope")
app.add_typer(commands.target_app, name="target")
app.add_typer(commands.action_app, name="actions")
app.add_typer(commands.preset_app, name="preset")
app.add_typer(commands.job_app, name="jobs")
app.add_typer(commands.report_app, name="report")


@app.command()
def version() -> None:
    """Show the Ambrosia version."""
    from ambrosia import __version__

    typer.echo(f"ambrosia {__version__}")


@app.command()
def hello() -> None:
    """Smoke-check that the CLI is wired up."""
    typer.echo("Ambrosia is ready. Use `ambrosia --help` to see available commands.")


def main() -> None:
    """Entry point for the ``ambrosia`` console script."""
    app()


if __name__ == "__main__":
    main()
