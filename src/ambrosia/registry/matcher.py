"""Pure action-availability matcher.

The matcher evaluates every registered action against a read-only
:class:`~ambrosia.registry.models.ContextSnapshot` and
:class:`~ambrosia.registry.models.PolicySnapshot`. It performs no I/O, executes
no tools, and has no side effects. For a fixed registry + snapshots the result
is deterministic.

Statuses (in ``ActionAvailability``):

* ``available`` — all requirements satisfied.
* ``needs_input`` — applicable, but a required user input is missing.
* ``needs_approval`` — applicable, but policy requires operator approval.
* ``blocked`` — scope or policy prohibits execution.
* ``missing_dependency`` — a required local tool/runtime is unavailable.
* ``not_applicable`` — required context (artifact/platform/pack) is absent.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from ambrosia.domain.action import ActionAvailability
from ambrosia.domain.errors import NotFoundError

# Statuses the matcher may report; kept as a single Literal so the most-severe
# status selection stays type-checked against ActionAvailability.status.
_Status = Literal[
    "available",
    "needs_input",
    "needs_approval",
    "blocked",
    "missing_dependency",
    "not_applicable",
]

if TYPE_CHECKING:
    from ambrosia.domain.action import ActionDefinition, ArtifactRequirement
    from ambrosia.domain.models import Artifact
    from ambrosia.registry.models import ContextSnapshot, PolicySnapshot
    from ambrosia.registry.registry import Registry

# Status priority: lower = more severe. The matcher reports every applicable
# reason but assigns the single most severe status.
_STATUS_PRIORITY = {
    "missing_dependency": 0,
    "blocked": 1,
    "needs_approval": 2,
    "needs_input": 3,
    "not_applicable": 4,
    "available": 5,
}


@dataclass
class _Finding:
    status: str
    reason: str


class AvailabilityMatcher:
    """Evaluates :class:`ActionAvailability` for registered actions."""

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------ public

    def evaluate(
        self,
        action_id: str,
        context: ContextSnapshot,
        policy: PolicySnapshot,
    ) -> ActionAvailability:
        """Return the availability of a single action.

        Raises :class:`~ambrosia.domain.errors.NotFoundError` if the action is
        unknown to the registry.
        """
        definition = self._registry.get(action_id)
        if definition is None:
            raise NotFoundError(f"action {action_id!r} is not registered")  # noqa: TRY003

        findings: list[_Finding] = []
        matched_ids: list[str] = []

        self._check_pack(definition, context, findings)
        self._check_platform(definition, context, findings)
        self._check_dependencies(definition, context, findings)
        self._check_scope(definition, context, policy, findings)
        matched_ids = self._check_artifacts(definition, context, findings)
        missing_inputs = self._check_inputs(definition, context, findings)
        required_approval = self._check_approval(definition, policy, findings)

        status = self._pick_status(findings)
        reasons = [f.reason for f in findings]

        return ActionAvailability(
            action_id=action_id,
            status=status,
            reasons=reasons,
            missing_inputs=missing_inputs,
            matched_artifact_ids=matched_ids,
            required_approval=required_approval,
        )

    def evaluate_all(
        self,
        context: ContextSnapshot,
        policy: PolicySnapshot,
    ) -> dict[str, ActionAvailability]:
        """Return availability for every visible (enabled-pack) action."""
        result: dict[str, ActionAvailability] = {}
        for action_id in [a.id for a in self._registry.list(enabled_only=True)]:
            result[action_id] = self.evaluate(action_id, context, policy)
        return result

    # ------------------------------------------------------------------ checks

    def _check_pack(
        self,
        definition: ActionDefinition,
        context: ContextSnapshot,
        findings: list[_Finding],
    ) -> None:
        pack_id = self._registry.action_pack_id(definition.id)
        if pack_id is not None and not self._registry._pack_enabled(pack_id):  # noqa: SLF001
            findings.append(
                _Finding("not_applicable", f"pack {pack_id!r} is disabled")
            )

    def _check_platform(
        self,
        definition: ActionDefinition,
        context: ContextSnapshot,
        findings: list[_Finding],
    ) -> None:
        if not definition.platforms:
            return  # no platform constraint -> runs everywhere
        if context.platform not in definition.platforms:
            findings.append(
                _Finding(
                    "not_applicable",
                    f"platform {context.platform!r} not supported "
                    f"(supported: {', '.join(definition.platforms)})",
                )
            )

    def _check_dependencies(
        self,
        definition: ActionDefinition,
        context: ContextSnapshot,
        findings: list[_Finding],
    ) -> None:
        for dep in definition.dependencies:
            if dep.name not in context.available_tools:
                findings.append(
                    _Finding(
                        "missing_dependency",
                        f"missing dependency: {dep.name}"
                        + (f" (version {dep.version})" if dep.version else ""),
                    )
                )

    def _check_scope(
        self,
        definition: ActionDefinition,
        context: ContextSnapshot,
        policy: PolicySnapshot,
        findings: list[_Finding],
    ) -> None:
        target = context.selected_target

        # An action that declares scope fields requires a target in scope.
        if definition.scope_fields and target is None:
            fields = ", ".join(definition.scope_fields)
            findings.append(
                _Finding(
                    "needs_input",
                    f"requires a target in scope for field(s): {fields}",
                )
            )
            return

        if target is None:
            return

        address = _target_address(target)
        if address is None:
            return

        if not _address_in_scope(address, policy):
            findings.append(
                _Finding(
                    "blocked",
                    f"blocked by scope: target {address} is outside the authorized scope",
                )
            )

        # Effect policy: effects not allowed at all block; effects needing
        # approval flag approval (handled in _check_approval as well).
        for effect in definition.effects:
            if effect not in policy.allowed_effects:
                findings.append(
                    _Finding(
                        "blocked",
                        f"blocked by policy: effect {effect!r} is not allowed in scope",
                    )
                )

    def _check_artifacts(
        self,
        definition: ActionDefinition,
        context: ContextSnapshot,
        findings: list[_Finding],
    ) -> list[str]:
        matched_ids: list[str] = []
        target_address = _target_address(context.selected_target) if context.selected_target else None

        for req in definition.required_artifacts:
            matches = _matching_artifacts(context.artifacts, req, target_address)
            matched_ids.extend(a.id for a in matches)
            if not matches:
                where = ""
                if req.where:
                    where = f" matching {req.where}"
                findings.append(
                    _Finding(
                        "not_applicable",
                        f"missing required artifact: {req.type}{where}",
                    )
                )
        return matched_ids

    def _check_inputs(
        self,
        definition: ActionDefinition,
        context: ContextSnapshot,
        findings: list[_Finding],
    ) -> list[str]:
        missing: list[str] = []
        schema = definition.input_schema or {}
        raw_required = schema.get("required", []) if isinstance(schema, dict) else []
        required = [str(field) for field in raw_required] if isinstance(raw_required, list) else []
        for field_name in required:
            if field_name not in context.inputs:
                missing.append(field_name)
                findings.append(
                    _Finding("needs_input", f"missing required input: {field_name}")
                )
        return missing

    def _check_approval(
        self,
        definition: ActionDefinition,
        policy: PolicySnapshot,
        findings: list[_Finding],
    ) -> bool:
        required = any(effect in policy.require_approval_for for effect in definition.effects)
        if required and definition.approval_required:
            findings.append(
                _Finding("needs_approval", "approval required before execution")
            )
            return True
        if required:
            findings.append(
                _Finding("needs_approval", "policy requires approval for declared effect(s)")
            )
        return required

    # ------------------------------------------------------------------ status

    @staticmethod
    def _pick_status(findings: list[_Finding]) -> _Status:
        if not findings:
            return "available"
        chosen = min(findings, key=lambda f: _STATUS_PRIORITY[f.status])
        return cast("_Status", chosen.status)


def _target_address(target: dict[str, object]) -> str | None:
    for key in ("address", "host", "id", "name"):
        value = target.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _address_in_scope(address: str, policy: PolicySnapshot) -> bool:
    """Return True if ``address`` is within the policy scope.

    Exclusions take precedence. When include lists are populated, the address
    must match at least one include entry. Empty include lists mean no target is
    authorized (conservative default).
    """
    # Exclusions first.
    for host in policy.exclude_hosts:
        if address == host:
            return False
    for cidr in policy.exclude_cidrs:
        if _cidr_contains(cidr, address):
            return False

    has_include = bool(policy.include_hosts or policy.include_cidrs or policy.include_domains)

    # Exact host match.
    for host in policy.include_hosts:
        if address == host:
            return True

    # CIDR containment.
    for cidr in policy.include_cidrs:
        if _cidr_contains(cidr, address):
            return True

    # Domain match: exact or suffix (e.g. example.com matches sub.example.com).
    for domain in policy.include_domains:
        if address == domain or address.endswith("." + domain):
            return True

    return not has_include  # empty include lists -> nothing authorized


def _cidr_contains(cidr: str, address: str) -> bool:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip in network


def _matching_artifacts(
    artifacts: tuple[Artifact, ...],
    req: ArtifactRequirement,
    target_address: str | None,
) -> list[Artifact]:
    matches: list[Artifact] = []
    for artifact in artifacts:
        if artifact.type != req.type:
            continue
        if req.same_target:
            if artifact.target_ref is None:
                continue
            if target_address is None or artifact.target_ref != target_address:
                continue
        if req.where and not _predicate_matches(artifact, req.where):
            continue
        matches.append(artifact)
    return matches


def _predicate_matches(artifact: Artifact, where: dict[str, object]) -> bool:
    value = artifact.value
    for key, expected in where.items():
        if isinstance(value, dict):
            actual = value.get(key)
        else:
            # Typed artifact wrappers expose their payload as a Pydantic model,
            # not a dict. Read the field by attribute name instead.
            actual = getattr(value, key, None)
        if actual != expected:
            return False
    return True


__all__ = [
    "AvailabilityMatcher",
]
