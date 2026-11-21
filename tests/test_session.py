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


def test_mark_dirty_and_mark_clean() -> None:
    session = SessionState()
    assert session.is_dirty is False

    session.mark_dirty()
    assert session.is_dirty is True

    session.mark_clean()
    assert session.is_dirty is False


def test_set_and_set_all_mark_dirty() -> None:
    session = SessionState()
    assert session.is_dirty is False

    session.set("nmap", "target", "127.0.0.1")
    assert session.is_dirty is True

    session.mark_clean()
    session.set_all("nmap", {"outfile": "scan.txt"})
    assert session.is_dirty is True


def test_clear_resets_values() -> None:
    session = SessionState()
    session.set("nmap", "target", "127.0.0.1")
    session.set("nmap", "outfile", "scan.txt")

    session.clear()

    assert session.get_all("nmap") == {}
    assert session.get("nmap", "target") is None


def test_to_dict_excludes_secrets() -> None:
    session = SessionState()
    session.register_secret_inputs("vault", {"password", "token"})
    session.set("vault", "password", "s3cret")
    session.set("vault", "host", "10.0.0.1")
    session.set("web", "target", "example.com")

    assert session.to_dict() == {
        "vault": {"password": "s3cret", "host": "10.0.0.1"},
        "web": {"target": "example.com"},
    }
    assert session.to_dict(exclude_secrets=True) == {
        "vault": {"host": "10.0.0.1"},
        "web": {"target": "example.com"},
    }


def test_save_excludes_secrets_by_default(tmp_path) -> None:
    path = tmp_path / "session.json"
    session = SessionState()
    session.register_secret_inputs("vault", {"password"})
    session.set("vault", "password", "s3cret")
    session.set("vault", "host", "10.0.0.1")

    store = SessionStore(path)
    store.save(session)

    restored = store.load()
    assert restored.get("vault", "host") == "10.0.0.1"
    assert restored.get("vault", "password") is None


def test_save_includes_secrets_when_requested(tmp_path) -> None:
    path = tmp_path / "session.json"
    session = SessionState()
    session.register_secret_inputs("vault", {"password"})
    session.set("vault", "password", "s3cret")

    store = SessionStore(path)
    store.save(session, exclude_secrets=False)

    restored = store.load()
    assert restored.get("vault", "password") == "s3cret"


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path) -> None:
    path = tmp_path / "session.json"
    store = SessionStore(path)
    store.save(SessionState())

    temp_files = [
        entry
        for entry in tmp_path.iterdir()
        if entry.name.startswith(path.name + ".") and entry.suffix == ".tmp"
    ]
    assert temp_files == []

    store.save(SessionState())
    assert tmp_path.joinpath("session.json").exists()
