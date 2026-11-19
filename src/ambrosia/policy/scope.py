"""Scope matching: exact IPs, CIDRs, hostnames/domains, exclusions, ports, expiry.

Validates targets against an engagement scope. Exclusions take precedence over
includes. Empty include lists mean nothing is authorized (conservative default).
DNS resolution is performed at a controlled boundary: hostnames are resolved to
IPs and both the name and its resolved addresses are checked against scope.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timezone, UTC

from ambrosia.domain.errors import ScopeViolationError
from ambrosia.domain.models import Scope


def _utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime (consistent with domain models)."""
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class ScopeCheckResult:
    """Result of checking a single address against a scope."""

    in_scope: bool
    reason: str | None = None
    resolved_addresses: tuple[str, ...] = ()


class ScopeChecker:
    """Validates targets against an engagement :class:`~ambrosia.domain.models.Scope`.

    Supports exact IP matches, CIDR containment, hostname/domain matching,
    exclusions (which take precedence), allowed ports, and expiry.
    """

    # ------------------------------------------------------------------ address

    def is_address_in_scope(self, address: str, scope: Scope) -> ScopeCheckResult:
        """Return whether ``address`` is authorized by ``scope``.

        Exclusions take precedence. When include lists are populated, the
        address must match at least one include entry. Empty include lists
        mean nothing is authorized.
        """
        # Exclusions first.
        for host in scope.exclude_hosts:
            if address == host:
                return ScopeCheckResult(
                    in_scope=False,
                    reason=f"address {address!r} is explicitly excluded",
                )
        for cidr in scope.exclude_cidrs:
            if self._cidr_contains(cidr, address):
                return ScopeCheckResult(
                    in_scope=False,
                    reason=f"address {address!r} is in excluded CIDR {cidr!r}",
                )

        has_include = bool(
            scope.include_hosts or scope.include_cidrs or scope.include_domains
        )

        # Exact host match.
        for host in scope.include_hosts:
            if address == host:
                return ScopeCheckResult(in_scope=True)

        # CIDR containment.
        for cidr in scope.include_cidrs:
            if self._cidr_contains(cidr, address):
                return ScopeCheckResult(in_scope=True)

        # Domain match: exact or suffix (e.g. example.com matches sub.example.com).
        for domain in scope.include_domains:
            if address == domain or address.endswith("." + domain):
                return ScopeCheckResult(in_scope=True)

        if not has_include:
            return ScopeCheckResult(
                in_scope=False,
                reason="scope has no include entries; nothing authorized",
            )
        return ScopeCheckResult(
            in_scope=False,
            reason=f"address {address!r} not matched by any include entry",
        )

    # ------------------------------------------------------------------ ports

    def is_port_allowed(self, port: int, scope: Scope) -> bool:
        """Return whether ``port`` is permitted by the scope.

        When ``allowed_ports`` is ``None`` there is no port restriction.
        """
        if scope.allowed_ports is None:
            return True
        return port in scope.allowed_ports

    # ------------------------------------------------------------------ expiry

    def is_expired(self, scope: Scope, now: datetime | None = None) -> bool:
        """Return whether the scope's expiry has passed."""
        if scope.expires_at is None:
            return False
        now = now or _utc_now_naive()
        return scope.expires_at <= now

    # ------------------------------------------------------------------ DNS

    def resolve_hostname(self, hostname: str) -> tuple[str, ...]:
        """Resolve a hostname to IP addresses (DNS resolution boundary).

        Returns an empty tuple when resolution fails. Only IP addresses are
        returned; the caller decides how to combine name and address checks.
        """
        try:
            infos = socket.getaddrinfo(hostname, None)
        except OSError:
            return ()
        addresses: set[str] = set()
        for info in infos:
            sockaddr = info[4]
            if sockaddr:
                addresses.add(str(sockaddr[0]))
        return tuple(sorted(addresses))

    def is_hostname_in_scope(
        self,
        hostname: str,
        scope: Scope,
    ) -> ScopeCheckResult:
        """Check a hostname against scope, including DNS resolution boundary.

        The hostname is checked directly (exact or domain-suffix match against
        ``include_hosts``/``include_domains``) and then resolved via DNS so its
        IP addresses are checked against ``include_hosts``/``include_cidrs``.
        Exclusions apply to both the name and resolved addresses.
        """
        # Direct name match (exact or domain suffix).
        direct = self.is_address_in_scope(hostname, scope)
        if direct.in_scope:
            return ScopeCheckResult(
                in_scope=True,
                resolved_addresses=self.resolve_hostname(hostname),
            )

        # Excluded names take precedence even without a direct include match.
        for host in scope.exclude_hosts:
            if hostname == host:
                return ScopeCheckResult(
                    in_scope=False,
                    reason=f"hostname {hostname!r} is explicitly excluded",
                )
        for cidr in scope.exclude_cidrs:
            if self._cidr_contains(cidr, hostname):
                return ScopeCheckResult(
                    in_scope=False,
                    reason=f"hostname {hostname!r} resolves into excluded CIDR {cidr!r}",
                )

        # DNS resolution boundary: resolve and check each address.
        resolved = self.resolve_hostname(hostname)
        for ip in resolved:
            addr_result = self.is_address_in_scope(ip, scope)
            if addr_result.in_scope:
                return ScopeCheckResult(
                    in_scope=True,
                    resolved_addresses=resolved,
                )

        has_include = bool(
            scope.include_hosts or scope.include_cidrs or scope.include_domains
        )
        if not has_include:
            return ScopeCheckResult(
                in_scope=False,
                reason="scope has no include entries; nothing authorized",
                resolved_addresses=resolved,
            )
        return ScopeCheckResult(
            in_scope=False,
            reason=f"hostname {hostname!r} (and resolved addresses) not matched by scope",
            resolved_addresses=resolved,
        )

    # ------------------------------------------------------------------ combined

    def check_target(
        self,
        address: str,
        *,
        port: int | None = None,
        scope: Scope,
        now: datetime | None = None,
        resolve_hostnames: bool = True,
    ) -> ScopeCheckResult:
        """Full target validation: expiry, address in scope, port allowed.

        Raises :class:`~ambrosia.domain.errors.ScopeViolationError` if any check
        fails so callers cannot forget to handle the failure.

        ``resolve_hostnames`` controls whether hostnames are resolved via DNS
        before the address check (the DNS resolution boundary).
        """
        if self.is_expired(scope, now=now):
            raise ScopeViolationError(
                f"engagement scope {scope.id} has expired",
                details={
                    "scope_id": scope.id,
                    "expires_at": scope.expires_at.isoformat()
                    if scope.expires_at is not None
                    else None,
                },
            )

        if resolve_hostnames and not self._looks_like_ip(address):
            result = self.is_hostname_in_scope(address, scope)
        else:
            result = self.is_address_in_scope(address, scope)

        if not result.in_scope:
            raise ScopeViolationError(
                result.reason or "address outside scope",
                details={
                    "address": address,
                    "scope_id": scope.id,
                    "resolved_addresses": list(result.resolved_addresses),
                },
            )

        if port is not None and not self.is_port_allowed(port, scope):
            raise ScopeViolationError(
                f"port {port} is not allowed by scope",
                details={
                    "port": port,
                    "scope_id": scope.id,
                    "allowed_ports": list(scope.allowed_ports or []),
                },
            )

        return result

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _cidr_contains(cidr: str, address: str) -> bool:
        try:
            network = ipaddress.ip_network(cidr, strict=False)
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return ip in network

    @staticmethod
    def _looks_like_ip(address: str) -> bool:
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False


__all__ = ["ScopeChecker", "ScopeCheckResult"]
