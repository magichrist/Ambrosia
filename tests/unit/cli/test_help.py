"""Tests for CLI invocation and help output."""

from __future__ import annotations

from typer.testing import CliRunner

from ambrosia.cli.main import app

runner = CliRunner()


def test_help_works() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Ambrosia" in result.output
    assert "engagement" in result.output
    assert "scope" in result.output
    assert "target" in result.output
    assert "actions" in result.output
    assert "preset" in result.output
    assert "jobs" in result.output
    assert "report" in result.output


def test_version_works() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ambrosia" in result.output


def test_subcommand_help_works() -> None:
    for command in [
        ["engagement", "create", "--help"],
        ["scope", "show", "--help"],
        ["target", "add", "--help"],
        ["actions", "info", "--help"],
        ["preset", "validate", "--help"],
        ["jobs", "show", "--help"],
        ["report", "export", "--help"],
    ]:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, command
        assert "--output" in result.output


def test_hello_works() -> None:
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "Ambrosia is ready" in result.output
