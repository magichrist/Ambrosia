# ruff: noqa: S101 -- assert is the standard pytest assertion idiom.

"""Unit tests for scope matching: include/exclude, DNS boundary, expiry."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from ambrosia.domain.errors import ScopeViolationError
from ambrosia.domain.models import Scope
from ambrosia.policy import ScopeChecker


def _scope(**overrides) -> Scope:
    data = dict(
        id="scope-1",
        engagement_id="eng-1",
        include_hosts=["10.0.0.1", "localhost"],
        include_cidrs=["10.0.0.0/24"],
        include_domains=["example.com"],
        exclude_hosts=["10.0.0.99"],
        exclude_cidrs=["10.0.0.128/25"],
        allowed_ports=[80, 443],
        max_concurrency=2,
        allowed_effects={"local_read", "network_observe"},
        require_approval_for={"local_write"},
    )
    data.update(overrides)
    return Scope(**data)


def _checker() -> ScopeChecker:
    return ScopeChecker()


# ---------------------------------------------------------------------------
# include_hosts / include_cidrs / include_domains

def test_include_exact_ip_match() -> None:
    result = _checker().is_address_in_scope("10.0.0.1", _scope())
    assert result.in_scope is True


def test_include_cidr_match() -> None:
    result = _checker().is_address_in_scope("10.0.0.42", _scope())
    assert result.in_scope is True


def test_include_cidr_non_match() -> None:
    result = _checker().is_address_in_scope("10.0.1.1", _scope())
    assert result.in_scope is False


def test_include_domain_exact_match() -> None:
    result = _checker().is_address_in_scope("example.com", _scope())
    assert result.in_scope is True


def test_include_domain_suffix_match() -> None:
    result = _checker().is_address_in_scope("sub.example.com", _scope())
    assert result.in_scope is True


def test_include_domain_non_match() -> None:
    result = _checker().is_address_in_scope("evil.com", _scope())
    assert result.in_scope is False


def test_empty_include_lists_authorize_nothing() -> None:
    result = _checker().is_address_in_scope("10.0.0.1", _scope(include_hosts=[], include_cidrs=[], include_domains=[]))
    assert result.in_scope is False
    assert result.reason is not None


# ---------------------------------------------------------------------------
# exclusions take precedence

def test_exclude_host_takes_precedence_over_include() -> None:
    result = _checker().is_address_in_scope("10.0.0.99", _scope())
    assert result.in_scope is False
    assert "explicitly excluded" in (result.reason or "")


def test_exclude_cidr_takes_precedence_over_include() -> None:
    result = _checker().is_address_in_scope("10.0.0.200", _scope())
    assert result.in_scope is False
    assert "excluded CIDR" in (result.reason or "")


# ---------------------------------------------------------------------------
# ports

def test_port_allowed_when_in_allowed_ports() -> None:
    assert _checker().is_port_allowed(80, _scope()) is True


def test_port_not_allowed_when_not_in_allowed_ports() -> None:
    assert _checker().is_port_allowed(22, _scope()) is False


def test_port_unrestricted_when_allowed_ports_none() -> None:
    assert _checker().is_port_allowed(12345, _scope(allowed_ports=None)) is True


# ---------------------------------------------------------------------------
# expiry

def test_scope_not_expired() -> None:
    future = datetime.utcnow() + timedelta(days=7)
    assert _checker().is_expired(_scope(expires_at=future)) is False


def test_scope_expired() -> None:
    past = datetime.utcnow() - timedelta(days=1)
    assert _checker().is_expired(_scope(expires_at=past)) is True


def test_scope_no_expiry() -> None:
    assert _checker().is_expired(_scope(expires_at=None)) is False


# ---------------------------------------------------------------------------
# check_target raises ScopeViolationError

def test_check_target_raises_when_outside_scope() -> None:
    checker = _checker()
    with pytest.raises(ScopeViolationError):
        checker.check_target("99.99.99.99", scope=_scope())


def test_check_target_raises_when_expired() -> None:
    checker = _checker()
    past = datetime.utcnow() - timedelta(days=1)
    with pytest.raises(ScopeViolationError):
        checker.check_target("10.0.0.1", scope=_scope(expires_at=past))


def test_check_target_raises_when_port_not_allowed() -> None:
    checker = _checker()
    with pytest.raises(ScopeViolationError):
        checker.check_target("10.0.0.1", port=22, scope=_scope())


def test_check_target_passes_when_in_scope() -> None:
    checker = _checker()
    result = checker.check_target("10.0.0.1", port=80, scope=_scope())
    assert result.in_scope is True


# ---------------------------------------------------------------------------
# hostname resolution boundary

def test_resolve_hostname_returns_addresses(monkeypatch) -> None:
    checker = _checker()

    def _fake_getaddrinfo(host, port):
        return [(None, None, None, None, ("10.0.0.1", 0))]

    monkeypatch.setattr("socket.getaddrinfo", _fake_getaddrinfo)
    addresses = checker.resolve_hostname("example.com")
    assert "10.0.0.1" in addresses


def test_resolve_hostname_failure_returns_empty() -> None:
    checker = _checker()

    def _fake_getaddrinfo(host, port):
        raise OSError("resolution failed")

    import socket

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)
    addresses = checker.resolve_hostname("does-not-exist.invalid")
    assert addresses == ()


def test_is_hostname_in_scope_direct_match() -> None:
    checker = _checker()
    result = checker.is_hostname_in_scope("localhost", _scope())
    assert result.in_scope is True


def test_is_hostname_in_scope_domain_suffix() -> None:
    checker = _checker()
    result = checker.is_hostname_in_scope("api.example.com", _scope())
    assert result.in_scope is True


def test_is_hostname_in_scope_excluded() -> None:
    checker = _checker()
    result = checker.is_hostname_in_scope("10.0.0.99", _scope())
    assert result.in_scope is False


def test_is_hostname_in_scope_not_found() -> None:
    checker = _checker()
    result = checker.is_hostname_in_scope("unknown.example.net", _scope())
    assert result.in_scope is False


# ---------------------------------------------------------------------------
# check_target with hostname resolution

def test_check_target_resolves_hostname(monkeypatch) -> None:
    checker = _checker()

    class _FakeSocket:
        @staticmethod
        def getaddrinfo(host, port):
            return [(None, None, None, None, ("10.0.0.42", 0))]

    import socket as socket_mod

    monkeypatch.setattr(socket_mod, "getaddrinfo", _FakeSocket.getaddrinfo)
    result = checker.check_target("host.example.com", scope=_scope())
    assert result.in_scope is True
    assert "10.0.0.42" in result.resolved_addresses
