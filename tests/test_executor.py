# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Tests for the v2 executor: ``build_argv`` substitution/split and subprocess wiring."""

from __future__ import annotations

import asyncio
import shutil

import pytest

from ambrosia.executor import (
    CommandResult,
    ExecutableNotFoundError,
    ShellExecutor,
    build_argv,
)


def test_build_argv_substitutes_and_splits() -> None:
    shell = "nmap -sV -oN {{outfile}} {{target}}"
    assert build_argv(shell, {"outfile": "scan.txt", "target": "127.0.0.1"}) == [
        "nmap",
        "-sV",
        "-oN",
        "scan.txt",
        "127.0.0.1",
    ]


def test_build_argv_splits_multiword_input() -> None:
    assert build_argv("echo {{msg}}", {"msg": "hello world"}) == [
        "echo",
        "hello",
        "world",
    ]


def test_build_argv_leaves_missing_token_in_place() -> None:
    assert build_argv("nmap {{target}}", {}) == ["nmap", "{{target}}"]
    assert build_argv("nmap -sV {{target}}", {"target": "127.0.0.1"}) == [
        "nmap",
        "-sV",
        "127.0.0.1",
    ]


def test_build_argv_empty_shell() -> None:
    assert build_argv("", {}) == []


class _StreamReader:
    def __init__(self, data: bytes = b"") -> None:
        self._data = data

    async def read(self, n: int = 4096) -> bytes:
        data = self._data[:n]
        self._data = self._data[n:]
        return data


class _FakeProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = None
        self._rc = returncode
        self.stdout = _StreamReader()
        self.stderr = _StreamReader()

    async def wait(self) -> int:
        self.returncode = self._rc
        return self._rc


@pytest.mark.asyncio
async def test_executor_runs_executable_with_resolved_argv(monkeypatch) -> None:
    captured: list[list[str]] = []

    async def fake_create_subprocess_exec(*argv, **kwargs):  # noqa: ARG001
        captured.append(list(argv))
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda exe: "/fake/" + exe)

    executor = ShellExecutor()
    result = await executor.run("nmap -sV {{target}}", {"target": "127.0.0.1"})

    assert isinstance(result, CommandResult)
    assert result.exit_code == 0
    assert result.cancelled is False
    assert captured == [["nmap", "-sV", "127.0.0.1"]]


@pytest.mark.asyncio
async def test_executor_streams_output(monkeypatch) -> None:
    chunks: list[str] = []

    async def fake_create_subprocess_exec(*argv, **kwargs):  # noqa: ARG001
        proc = _FakeProcess()
        proc.stdout = _StreamReader(b"line1\nline2\n")
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", lambda exe: "/fake/" + exe)

    executor = ShellExecutor()
    result = await executor.run("echo {{msg}}", {"msg": "hi"}, on_output=chunks.append)

    assert result.exit_code == 0
    assert "line1" in "".join(chunks)


@pytest.mark.asyncio
async def test_executor_unknown_executable_raises(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda *_: None)
    executor = ShellExecutor()
    with pytest.raises(ExecutableNotFoundError):
        await executor.run("nonexistent-tool {{x}}", {"x": "1"})
