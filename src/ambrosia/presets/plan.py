"""Deterministic preset plans (DAGs over step nodes).

A plan is the validated, executable representation of a preset: steps ordered
topologically by their ``needs`` dependencies plus implicit dependencies
wired from step output references and condition branches. Step types are
``action``, ``condition``, ``approval``, and ``output``.

The plan is side-effect free: building it never invokes an action handler or
executor. The preset-level effect summary is the union of the effects
declared by the action steps.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from ambrosia.presets.errors import (
    CyclicDependencyError,
    DuplicateStepIdError,
    InvalidPredicateError,
    InvalidReferenceError,
    UnresolvedActionError,
)
from ambrosia.presets.predicates import Predicate, parse_predicate
from ambrosia.presets.references import (
    VariableReference,
    parse_reference,
    step_id_from_steps_reference,
)

if TYPE_CHECKING:
    from ambrosia.domain.preset import (
        OutputBinding,
        PresetDefinition,
        PresetStep,
    )
    from ambrosia.registry.registry import Registry

_BINDING_PREFIX = "{{"
_BINDING_SUFFIX = "}}"

# Step types that must not declare an ``action`` reference.
_NO_ACTION_TYPES = frozenset({"condition", "approval", "output"})

# Branch map: step id -> (then step ids, else step ids).
BranchMap = Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]]


@dataclass(frozen=True)
class Binding:
    """A typed input binding: either a literal value or a variable reference."""

    kind: Literal["literal", "reference"]
    value: Any = None
    reference: VariableReference | None = None


@dataclass(frozen=True)
class StepNode:
    """A single validated step in a preset plan."""

    id: str
    type: Literal["action", "condition", "approval", "output"]
    action_id: str | None = None
    # Ordered dependencies on earlier step ids (explicit plus output-derived
    # and condition-gated dependencies).
    needs: tuple[str, ...] = field(default_factory=tuple)
    # Constrained predicate gate; the step only runs when this is true.
    when: Predicate | None = None
    # Input name -> binding.
    inputs: dict[str, Binding] = field(default_factory=dict)
    # Named outputs published by this step.
    outputs: dict[str, OutputBinding] = field(default_factory=dict)
    on_failure: Literal["stop", "continue"] = "stop"
    # Condition branches: step ids selected when the condition is true/false.
    then: tuple[str, ...] = field(default_factory=tuple)
    else_: tuple[str, ...] = field(default_factory=tuple)
    # Effects declared by the referenced action (action steps only).
    effects: tuple[str, ...] = field(default_factory=tuple)
    # Condition step that gates this step (set when the step is in a branch).
    gated_by: str | None = None


@dataclass(frozen=True)
class PresetPlan:
    """Deterministic plan representation of a preset.

    ``order`` is a topological ordering of step ids, tie-broken by declaration
    order so the same document always yields the same plan. ``effects`` is the
    union of the effects declared by the plan's action steps.
    """

    preset_id: str
    steps: dict[str, StepNode]
    order: tuple[str, ...]
    effects: frozenset[str]
    required_inputs: tuple[str, ...]


def build_plan(
    definition: PresetDefinition,
    registry: Registry,
    branches: BranchMap | None = None,
) -> PresetPlan:
    """Build a deterministic :class:`PresetPlan` from a validated definition.

    ``branches`` maps condition step ids to their ``(then, else)`` branch step
    ids (captured by the loader since the domain step model does not carry
    them).

    Validates: unique step ids, existing ``needs`` targets, action id
    resolution against the registry, step-type constraints, reference syntax
    in bindings/output sources, predicate grammar, condition branches, and
    dependency cycles. Never executes an action or handler.
    """
    branch_map = dict(branches or {})
    steps = _validate_and_parse_steps(definition, registry, branch_map)
    order = _topological_order(steps)
    effects = _collect_effects(steps, registry)
    required_inputs = _required_inputs(definition)
    return PresetPlan(
        preset_id=definition.metadata.id,
        steps=steps,
        order=order,
        effects=frozenset(effects),
        required_inputs=tuple(required_inputs),
    )


def _validate_and_parse_steps(
    definition: PresetDefinition,
    registry: Registry,
    branches: BranchMap,
) -> dict[str, StepNode]:
    step_ids = [step.id for step in definition.steps]
    if len(step_ids) != len(set(step_ids)):
        duplicates = sorted(
            step_id for step_id in step_ids if step_ids.count(step_id) > 1
        )
        raise DuplicateStepIdError(  # noqa: TRY003
            f"duplicate step ids: {', '.join(duplicates)}"
        )

    known = set(step_ids)
    nodes: dict[str, StepNode] = {}
    for raw_step in definition.steps:
        then, else_ = branches.get(raw_step.id, ((), ()))
        step = _parse_step(raw_step, known, registry, then, else_)
        nodes[step.id] = step

    # Second pass: validate ``needs`` targets, wire implicit dependencies from
    # step output references, and record condition gating targets.
    output_implicit: dict[str, list[str]] = {}
    gated_by: dict[str, str] = {}
    for step in list(nodes.values()):
        implicit: list[str] = []
        for dependency in step.needs:
            if dependency not in known:
                raise InvalidReferenceError(  # noqa: TRY003
                    f"step {step.id!r} needs unknown step {dependency!r}"
                )
        for binding in step.inputs.values():
            if (
                binding.kind == "reference"
                and binding.reference is not None
                and binding.reference.namespace == "steps"
            ):
                dep = step_id_from_steps_reference(binding.reference)
                if dep not in known:
                    raise InvalidReferenceError(  # noqa: TRY003
                        f"step {step.id!r} references outputs of unknown "
                        f"step {dep!r}"
                    )
                if dep == step.id:
                    raise CyclicDependencyError(  # noqa: TRY003
                        f"step {step.id!r} references its own output"
                    )
                if dep not in step.needs:
                    implicit.append(dep)
        if step.type == "condition":
            then, else_ = branches.get(step.id, ((), ()))
            for branch_step_id in (*then, *else_):
                if branch_step_id not in known:
                    raise InvalidReferenceError(  # noqa: TRY003
                        f"condition step {step.id!r} branches reference "
                        f"unknown step {branch_step_id!r}"
                    )
                if branch_step_id == step.id:
                    raise CyclicDependencyError(  # noqa: TRY003
                        f"condition step {step.id!r} branches to itself"
                    )
                if branch_step_id in gated_by:
                    raise InvalidReferenceError(  # noqa: TRY003
                        f"step {branch_step_id!r} is in branches of multiple "
                        f"conditions"
                    )
                gated_by[branch_step_id] = step.id
        output_implicit[step.id] = implicit

    # Apply gating: branch steps depend on their condition.
    for step_id, step in list(nodes.items()):
        needs = list(step.needs) + output_implicit[step_id]
        if step_id in gated_by and gated_by[step_id] not in needs:
            needs.append(gated_by[step_id])
        if output_implicit[step_id] or step_id in gated_by:
            nodes[step_id] = replace(
                step, needs=tuple(needs), gated_by=gated_by.get(step_id)
            )

    return nodes


def _parse_step(
    raw_step: PresetStep,
    known_step_ids: set[str],
    registry: Registry,
    then: tuple[str, ...],
    else_: tuple[str, ...],
) -> StepNode:
    step_type = raw_step.type
    label = f"step {raw_step.id!r}"

    if step_type == "action":
        if not raw_step.action:
            raise InvalidReferenceError(f"{label}: action steps require an action id")  # noqa: TRY003
        if not registry.has(raw_step.action):
            raise UnresolvedActionError(  # noqa: TRY003
                f"{label}: action {raw_step.action!r} is not registered"
            )
        action_id = raw_step.action
    else:
        if raw_step.action:
            raise InvalidReferenceError(  # noqa: TRY003
                f"{label}: {step_type} steps must not declare an action"
            )
        action_id = None

    if step_type == "condition" and raw_step.when is None:
        raise InvalidPredicateError(  # noqa: TRY003
            f"{label}: condition steps require a 'when' predicate"
        )

    parsed_when: Predicate | None = None
    if raw_step.when is not None:
        parsed_when = parse_predicate(raw_step.when)

    bindings: dict[str, Binding] = {}
    for name, value in raw_step.inputs.items():
        bindings[name] = _parse_binding(value)

    output_bindings: dict[str, OutputBinding] = {}
    for name, output in raw_step.outputs.items():
        _parse_binding(output.source)  # validates reference syntax
        output_bindings[name] = output

    return StepNode(
        id=raw_step.id,
        type=step_type,
        action_id=action_id,
        needs=tuple(raw_step.needs),
        when=parsed_when,
        inputs=bindings,
        outputs=output_bindings,
        on_failure=raw_step.on_failure,
        then=then,
        else_=else_,
    )


def _parse_binding(value: object) -> Binding:
    if isinstance(value, str):
        if "{{" in value or "}}" in value:
            # Only a complete {{...}} token may be substituted; free-form
            # interpolation is rejected.
            return Binding(
                kind="reference", reference=parse_reference(value)
            )
        return Binding(kind="literal", value=value)
    return Binding(kind="literal", value=value)


def _topological_order(steps: dict[str, StepNode]) -> tuple[str, ...]:
    """Kahn's algorithm with declaration-order tie-breaking (deterministic)."""

    declaration_index = {
        step_id: index for index, step_id in enumerate(steps)
    }
    incoming: dict[str, set[str]] = {step_id: set() for step_id in steps}
    dependents: dict[str, list[str]] = {step_id: [] for step_id in steps}
    for step_id, step in steps.items():
        for dependency in step.needs:
            if dependency == step_id:
                continue  # self-loops are rejected earlier
            if dependency in steps:
                incoming[step_id].add(dependency)
                dependents[dependency].append(step_id)

    ready: list[str] = [
        step_id for step_id in steps if not incoming[step_id]
    ]
    order: list[str] = []
    while ready:
        ready.sort(key=lambda sid: declaration_index[sid])
        step_id = ready.pop(0)
        order.append(step_id)
        for dependent in dependents[step_id]:
            incoming[dependent].discard(step_id)
            if not incoming[dependent]:
                ready.append(dependent)

    if len(order) != len(steps):
        remaining = sorted(set(steps) - set(order))
        raise CyclicDependencyError(  # noqa: TRY003
            f"cyclic step dependencies involving: {', '.join(remaining)}"
        )
    return tuple(order)


def _collect_effects(steps: dict[str, StepNode], registry: Registry) -> list[str]:
    effects: list[str] = []
    for step in steps.values():
        if step.type == "action" and step.action_id is not None:
            definition = registry.get(step.action_id)
            if definition is not None:
                effects.extend(definition.effects)
    return effects


def _required_inputs(definition: PresetDefinition) -> list[str]:
    return sorted(
        name
        for name, input_decl in definition.inputs.items()
        if input_decl.required and input_decl.default is None
    )


__all__ = [
    "Binding",
    "StepNode",
    "PresetPlan",
    "BranchMap",
    "build_plan",
]
