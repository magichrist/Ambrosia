# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the v2 ``Command`` and ``CommandInput`` dataclasses."""

from __future__ import annotations

from ambrosia.model import Command, CommandInput, inputs_from_shell


def test_command_input_defaults() -> None:
    inp = CommandInput(id="ip", prompt="Target IP or hostname")
    assert inp.id == "ip"
    assert inp.prompt == "Target IP or hostname"
    assert inp.type == "string"
    assert inp.required is True
    assert inp.secret is False
    assert inp.default is None


def test_command_input_explicit_fields() -> None:
    inp = CommandInput(
        id="password",
        prompt="Password",
        type="secret",
        required=True,
        secret=True,
        default=None,
    )
    assert inp.type == "secret"
    assert inp.secret is True


def test_command_defaults() -> None:
    cmd = Command(id="smb", name="smb scan", description="uses crackmapexec smb")
    assert cmd.tags == []
    assert cmd.shell == ""
    assert cmd.inputs == []


def test_command_full() -> None:
    cmd = Command(
        id="smb-version",
        name="windows version check smb",
        description="uses crackmapexec smb to get windows version",
        shell="crackmapexec smb {{ip}}",
        tags=["smb", "windows", "crackmapexec"],
        inputs=[CommandInput(id="ip", prompt="Target IP or hostname", required=True)],
    )
    assert cmd.id == "smb-version"
    assert cmd.shell == "crackmapexec smb {{ip}}"
    assert cmd.tags == ["smb", "windows", "crackmapexec"]
    assert cmd.input_by_id("ip") is not None
    assert cmd.input_by_id("missing") is None
    assert len(cmd.required_inputs()) == 1
    assert cmd.required_inputs()[0].id == "ip"


def test_command_all_inputs_filled() -> None:
    cmd = Command(
        id="smb",
        name="smb scan",
        description="smb scan description",
        shell="crackmapexec smb {{ip}}",
        inputs=[CommandInput(id="ip", prompt="Target IP", required=True)],
    )
    assert cmd.all_inputs_filled({"ip": "10.0.0.5"}) is True
    assert cmd.all_inputs_filled({}) is False
    assert cmd.all_inputs_filled({"ip": ""}) is False


def test_command_serialization_round_trip() -> None:
    cmd = Command(
        id="smb-version",
        name="windows version check smb",
        description="uses crackmapexec smb",
        shell="crackmapexec smb {{ip}}",
        tags=["smb"],
        inputs=[CommandInput(id="ip", prompt="Target IP", required=True)],
    )
    restored = Command.from_dict(cmd.to_dict())
    assert restored == cmd


def test_inputs_from_shell_returns_unique_placeholders_in_order() -> None:
    inputs = inputs_from_shell("cme smb {{target}} -u {{user}} -p {{target}}")
    assert [inp.id for inp in inputs] == ["target", "user"]
    assert inputs[0].prompt == "target"
    assert inputs[0].type == "string"
    assert inputs[0].required is True
    assert inputs[0].secret is False


def test_inputs_from_shell_ignores_incomplete_tokens() -> None:
    assert inputs_from_shell("echo {{ }} {{not-valid}} {single}") == []
