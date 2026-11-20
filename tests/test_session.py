# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Tests for the v2 ``SessionState``: get/set/has_all_required and JSON round-trip."""

from __future__ import annotations

from ambrosia.session import SessionState, SessionStore


def test_get_set_and_has_all_required() -> None:
    session = SessionState()
    assert session.get("nmap", "target") is None
    assert session.has_all_required("nmap", ["target", "outfile"]) is False

    session.set("nmap", "target", "127.0.0.1")
    assert session.get("nmap", "target") == "127.0.0.1"
    assert session.has_all_required("nmap", ["target", "outfile"]) is False

    session.set("nmap", "outfile", "scan.txt")
    assert session.has_all_required("nmap", ["target", "outfile"]) is True
    assert session.get_all("nmap") == {"target": "127.0.0.1", "outfile": "scan.txt"}


def test_get_returns_none_for_missing_key() -> None:
    assert SessionState().get("nmap", "absent") is None


def test_has_all_required_empty_when_no_required() -> None:
    assert SessionState().has_all_required("anything", []) is True
    assert SessionState().has_all_required("anything", ["missing"]) is False


def test_json_persistence_round_trip(tmp_path) -> None:
    path = tmp_path / "session.json"
    session = SessionState()
    session.set("nmap", "target", "127.0.0.1")
    session.set("nmap", "outfile", "scan.txt")

    store = SessionStore(path)
    store.save(session)

    restored = store.load()
    assert restored.get("nmap", "target") == "127.0.0.1"
    assert restored.get("nmap", "outfile") == "scan.txt"
    assert restored.has_all_required("nmap", ["target", "outfile"]) is True

    # A second save/load cycle preserves the data.
    store.save(restored)
    again = store.load()
    assert again.get("nmap", "target") == "127.0.0.1"


def test_missing_session_file_loads_empty(tmp_path) -> None:
    assert SessionStore(tmp_path / "nonexistent.json").load().get_all("x") == {}
