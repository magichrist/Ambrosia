# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for the Nmap adapter: XML parsing and argv construction.

All tests use static fixtures; no live target and no Nmap execution is
required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ambrosia.executors.adapters import NmapAdapter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "packs" / "windows_assessment"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------


def test_build_argv_is_bounded_and_shell_free() -> None:
    adapter = NmapAdapter()
    argv = adapter.build_argv(target="10.0.0.10", ports="80,445")
    assert argv[0] == "-oX"
    assert argv[1] == "-"
    assert "-Pn" in argv
    assert "-sV" in argv
    assert "-p" in argv
    assert "80,445" in argv
    assert argv[-1] == "10.0.0.10"
    # No shell metacharacters are ever interpolated; every element is data.
    assert all(isinstance(arg, str) for arg in argv)


def test_build_argv_includes_scripts_when_provided() -> None:
    adapter = NmapAdapter()
    argv = adapter.build_argv(target="10.0.0.10", ports="445", scripts="smb-os-discovery")
    assert "--script" in argv
    assert "smb-os-discovery" in argv


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------


def test_parse_service_discovery_fixture() -> None:
    adapter = NmapAdapter()
    result = adapter.parse_output(_fixture("nmap_service_discovery.xml"))

    open_services = result.open_services
    ports = {s.port for s in open_services}
    assert ports == {445, 80, 3389, 5985}

    smb = next(s for s in open_services if s.port == 445)
    assert smb.service_name == "microsoft-ds"
    assert smb.product == "Samba"
    assert smb.version == "4.6.2"
    assert smb.state == "open"
    assert smb.host == "10.0.0.10"
    assert "smb-os-discovery" in smb.scripts

    http = next(s for s in open_services if s.port == 80)
    assert http.service_name == "http"

    # A filtered port must not appear as an open service.
    assert not any(s.port == 135 for s in open_services)


def test_parse_smb_only_fixture() -> None:
    adapter = NmapAdapter()
    result = adapter.parse_output(_fixture("nmap_smb_only.xml"))

    services = result.open_services
    assert len(services) == 1
    assert services[0].port == 445
    assert services[0].host == "10.0.0.20"
    assert result.hosts[0].os_matches
    assert "domain controller" in result.hosts[0].os_matches[0]


def test_parse_empty_fixture() -> None:
    adapter = NmapAdapter()
    result = adapter.parse_output(_fixture("nmap_empty.xml"))
    # The host is up but no ports are open, so there are no open services.
    assert len(result.hosts) == 1
    # `services` includes filtered/closed entries; only `open_services` is
    # filtered to open ports.
    assert result.open_services == []
    assert len(result.services) == 1
    assert result.services[0].state == "filtered"


def test_parse_empty_string() -> None:
    adapter = NmapAdapter()
    from ambrosia.executors.adapters.base import NmapParseResult

    empty = NmapParseResult()
    assert adapter.parse_output("") == empty
    assert adapter.parse_output("   ") == empty


def test_parse_malformed_raises() -> None:
    adapter = NmapAdapter()
    with pytest.raises(ValueError):
        adapter.parse_output(_fixture("nmap_malformed.xml"))


def test_parse_malformed_garbage() -> None:
    adapter = NmapAdapter()
    with pytest.raises(ValueError):
        adapter.parse_output("<nmaprun><host><port portid=")  # truncated XML


# ---------------------------------------------------------------------------
# script output is treated as opaque data, never as commands
# ---------------------------------------------------------------------------


def test_script_output_is_opaque_text() -> None:
    adapter = NmapAdapter()
    result = adapter.parse_output(_fixture("nmap_service_discovery.xml"))
    smb = next(s for s in result.open_services if s.port == 445)
    output = smb.scripts["smb-os-discovery"]
    assert "Domain name: CORP.LOCAL" in output
    assert "Forest name: CORP.LOCAL" in output
    # Script output is raw evidence text embedded in structured XML; it is never
    # interpreted as a command or executed.
