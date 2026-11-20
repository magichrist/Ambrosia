"""Preset loader, validator, and dry-run planner.

Presets are YAML/JSON documents validated into the domain
:class:`~ambrosia.domain.preset.PresetDefinition` model. Only
``yaml.safe_load`` is used; Python object tags (``!!python/object`` and
friends) are rejected at the YAML layer.

The loader builds a deterministic :class:`~ambrosia.presets.plan.PresetPlan`
(DAG) and can run a dry-run that resolves bindings to typed values without
executing any action. Missing inputs surface as :class:`InputRequest`,
ambiguous artifacts as :class:`ArtifactSelectionRequest`, and secrets resolve
to opaque :class:`SecretHandle` instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]  # types-PyYAML stubs are not a project dependency

from ambrosia.domain.errors import ParseError
from ambrosia.domain.preset import PresetDefinition, PresetInput
from ambrosia.presets.errors import (
    ArtifactSelectionRequest,
    InputRequest,
    PresetError,
    PresetValidationError,
    TypeMismatchError,
)
from ambrosia.presets.normalize import normalize_engine_step_keys
from ambrosia.presets.plan import PresetPlan, StepNode, build_plan
from ambrosia.presets.predicates import evaluate_predicate
from ambrosia.presets.references import parse_reference
from ambrosia.presets.resolution import (
    DeferredStepOutput,
    ResolutionContext,
    ResolvedValue,
    Resolver,
    check_type,
)

if TYPE_CHECKING:
    from ambrosia.domain.models import Artifact
    from ambrosia.registry.registry import Registry

_JSON_SCHEMA_TYPE_MAP: dict[str, str] = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "object": "object",
    "array": "array",
}

@dataclass(frozen=True)
class LoadedPreset:
    """A preset document with its validated deterministic plan."""

    definition: PresetDefinition
    plan: PresetPlan


@dataclass(frozen=True)
class DryRunResult:
    """Result of a dry-run: resolved bindings plus any outstanding requests.

    A dry-run never invokes an action handler or executor. ``requests`` are
    structured prompts (missing inputs, ambiguous artifact selections) that a
    TUI or CLI can surface to the operator in a typed form.
    """

    preset_id: str
    plan: PresetPlan
    resolved: dict[str, dict[str, object]] = field(default_factory=dict)
    # step id -> bound output name -> value (condition/output steps only)
    step_outputs: dict[str, dict[str, object]] = field(default_factory=dict)
    requests: tuple[InputRequest | ArtifactSelectionRequest, ...] = field(
        default_factory=tuple
    )
    errors: tuple[PresetError, ...] = field(default_factory=tuple)
    active_steps: tuple[str, ...] = field(default_factory=tuple)
    condition_results: dict[str, bool] = field(default_factory=dict)


class PresetLoader:
    """Loads and validates preset documents against a registered action set."""

    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------ load

    def load_text(self, text: str, source: str = "<preset>") -> LoadedPreset:
        """Load a preset from YAML/JSON text.

        Raises :class:`~ambrosia.domain.errors.ParseError` for invalid YAML
        (including Python object tags) and
        :class:`PresetValidationError` for schema or semantic problems.
        """
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ParseError(f"{source}: invalid YAML: {exc}") from exc  # noqa: TRY003

        return self._build(data, source)

    def load_file(self, path: str | Path, source: str | None = None) -> LoadedPreset:
        """Load a preset from a YAML/JSON file."""
        path = Path(path)
        source = source or str(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ParseError(f"{source}: cannot read preset: {exc}") from exc  # noqa: TRY003
        return self.load_text(text, source=source)

    def _build(self, data: Any, source: str) -> LoadedPreset:
        if not isinstance(data, dict):
            raise PresetValidationError(  # noqa: TRY003
                f"{source}: preset document must be a mapping, "
                f"got {type(data).__name__}"
            )
        data = dict(data)
        branches = normalize_engine_step_keys(data)
        try:
            definition = PresetDefinition.model_validate(data)
        except Exception as exc:  # pragma: no cover - pydantic raises ValidationError
            raise PresetValidationError(  # noqa: TRY003
                f"{source}: invalid preset document: {exc}"
            ) from exc

        plan = build_plan(definition, self._registry, branches=branches)
        return LoadedPreset(definition=definition, plan=plan)

    # ------------------------------------------------------------------ dry-run

    def dry_run(
        self,
        definition: PresetDefinition,
        plan: PresetPlan,
        *,
        inputs: dict[str, object] | None = None,
        context: dict[str, object] | None = None,
        target: dict[str, object] | None = None,
        artifacts: dict[str, Artifact] | None = None,
    ) -> DryRunResult:
        """Resolve every binding without executing any action.

        Returns a :class:`DryRunResult` with resolved values, structured
        requests for missing/ambiguous inputs, and any type mismatches. The
        result is deterministic for a fixed context.
        """
        provided_inputs = dict(inputs or {})
        context_snapshot = dict(context or {})
        target_snapshot = dict(target or {})
        artifacts_snapshot = dict(artifacts or {})
        preset_metadata = _metadata_dict(definition.metadata)
        declared_inputs: dict[str, PresetInput] = dict(definition.inputs)

        condition_results: dict[str, bool] = {}
        for step in plan.steps.values():
            if step.type == "condition" and step.when is not None:
                condition_results[step.id] = evaluate_predicate(
                    step.when,
                    artifacts=list(artifacts_snapshot.values()),
                    inputs=provided_inputs,
                )

        active_steps = self._active_steps(
            plan, condition_results, artifacts_snapshot, provided_inputs
        )

        bound_outputs: dict[str, dict[str, object]] = {}
        resolved: dict[str, dict[str, object]] = {}
        step_outputs: dict[str, dict[str, object]] = {}
        requests: list[InputRequest | ArtifactSelectionRequest] = []
        errors: list[PresetError] = []

        for step_id in plan.order:
            step = plan.steps[step_id]
            if step_id not in active_steps:
                continue

            resolver = Resolver(
                context=ResolutionContext(
                    inputs=provided_inputs,
                    context=context_snapshot,
                    target=target_snapshot,
                    artifacts=artifacts_snapshot,
                    step_outputs=bound_outputs,
                    preset=preset_metadata,
                    declared_inputs=declared_inputs,
                )
            )

            binding_results: dict[str, object] = {}
            for name, binding in step.inputs.items():
                expected_type = self._expected_type(step, name, definition)
                payload: Any = (
                    binding.value if binding.kind == "literal" else binding.reference
                )
                result = resolver.resolve(payload)
                if isinstance(result, ResolvedValue):
                    if expected_type is not None:
                        mismatch = check_type(result.value, expected_type)
                        if mismatch is not None:
                            errors.append(
                                TypeMismatchError(
                                    f"step {step_id!r} input {name!r}: expected "
                                    f"{mismatch.expected_type}, got "
                                    f"{mismatch.actual_type}",
                                    details={
                                        "step": step_id,
                                        "input": name,
                                        "expected_type": mismatch.expected_type,
                                        "actual_type": mismatch.actual_type,
                                    },
                                )
                            )
                    binding_results[name] = result.value
                elif isinstance(result, InputRequest):
                    requests.append(result)
                elif isinstance(result, ArtifactSelectionRequest):
                    requests.append(result)
                elif isinstance(result, DeferredStepOutput):
                    # Action outputs are bound at execution time; keep a
                    # placeholder so downstream references stay resolvable.
                    binding_results[name] = result
                else:  # pragma: no cover - exhaustive union
                    raise PresetError(f"unexpected resolution result {result!r}")  # noqa: TRY003

            resolved[step_id] = binding_results

            if step.type == "condition":
                step_outputs[step_id] = {
                    "result": condition_results.get(step_id, False)
                }
                bound_outputs[step_id] = step_outputs[step_id]
            elif step.type == "output":
                bound: dict[str, object] = {}
                for name, output in step.outputs.items():
                    result = resolver.resolve(parse_reference(output.source))
                    if isinstance(result, ResolvedValue):
                        bound[name] = result.value
                    elif isinstance(result, DeferredStepOutput):
                        bound[name] = result
                    elif isinstance(result, (InputRequest, ArtifactSelectionRequest)):
                        requests.append(result)
                step_outputs[step_id] = bound
                bound_outputs[step_id] = bound

        return DryRunResult(
            preset_id=definition.metadata.id,
            plan=plan,
            resolved=resolved,
            step_outputs=step_outputs,
            requests=tuple(requests),
            errors=tuple(errors),
            active_steps=tuple(sorted(active_steps)),
            condition_results=condition_results,
        )

    # ------------------------------------------------------------------ helpers

    def _active_steps(
        self,
        plan: PresetPlan,
        condition_results: dict[str, bool],
        artifacts: dict[str, Artifact],
        inputs: dict[str, object],
    ) -> set[str]:
        """Determine which steps are active, in dependency order.

        A step is inactive when its ``when`` predicate is false, or when it is
        in a condition branch that was not selected.
        """
        active: set[str] = set()
        for step_id in plan.order:
            step = plan.steps[step_id]
            active_here = True

            if step.gated_by is not None:
                condition_met = condition_results.get(step.gated_by, False)
                then_ids = plan.steps[step.gated_by].then
                else_ids = plan.steps[step.gated_by].else_
                if step_id not in then_ids and step_id not in else_ids:
                    active_here = False
                elif condition_met and step_id not in then_ids:
                    active_here = False
                elif not condition_met and step_id not in else_ids:
                    active_here = False

            if (
                active_here
                and step.when is not None
                and step.type != "condition"
            ):
                active_here = evaluate_predicate(
                    step.when,
                    artifacts=list(artifacts.values()),
                    inputs=inputs,
                )

            if active_here:
                active.add(step_id)
        return active

    def _expected_type(
        self, step: StepNode, name: str, definition: PresetDefinition
    ) -> str | None:
        input_decl = definition.inputs.get(name)
        if input_decl is not None:
            return str(input_decl.type)
        if step.type == "action" and step.action_id is not None:
            action_definition = self._registry.get(step.action_id)
            if action_definition is not None:
                schema = action_definition.input_schema or {}
                if isinstance(schema, dict):
                    properties = schema.get("properties")
                    if isinstance(properties, dict):
                        prop = properties.get(name)
                        if isinstance(prop, dict):
                            json_type = prop.get("type")
                            if isinstance(json_type, str):
                                return _JSON_SCHEMA_TYPE_MAP.get(json_type, json_type)
        return None


def _metadata_dict(metadata: Any) -> dict[str, object]:
    # The ``preset.*`` namespace root is the metadata table, so
    # ``preset.metadata.id`` traverses ``preset`` -> ``metadata`` -> ``id``.
    return {
        "metadata": {
            "id": metadata.id,
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "author": metadata.author,
            "tags": list(metadata.tags),
        }
    }


__all__ = [
    "LoadedPreset",
    "DryRunResult",
    "PresetLoader",
]
