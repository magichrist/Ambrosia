"""Application service for presets.

Presets are declarative ``ambrosia/v1`` YAML documents. This service validates,
plans (dry-run), and runs them. Execution is delegated to an optional engine
(Agent 5's ``ambrosia.engine``); when no engine is integrated, ``run`` raises a
typed missing-dependency error instead of silently succeeding.
"""

from __future__ import annotations

import re
import uuid
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, cast

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

from ambrosia.application._base import _BaseService
from ambrosia.domain.errors import NotFoundError, ValidationError
from ambrosia.domain.models import ExecutionRecord
from ambrosia.domain.preset import PresetDefinition, PresetStep
from ambrosia.domain.protocols import (  # noqa: TC001 - used at runtime via cast()
    ArtifactRepository as ArtifactRepositoryProtocol,
)
from ambrosia.domain.protocols import (  # noqa: TC001 - used at runtime via cast()
    EngagementRepository as EngagementRepositoryProtocol,
)
from ambrosia.domain.protocols import (  # noqa: TC001 - used at runtime via cast()
    ScopeRepository as ScopeRepositoryProtocol,
)

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable

    from ambrosia.application.protocols import PresetEngine
    from ambrosia.registry import Registry

_REFERENCE_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_VALID_NAMESPACES = frozenset({"inputs", "context", "target", "artifacts", "steps", "preset", "secrets"})


class PresetDTO(BaseModel):
    id: str
    name: str
    version: str
    description: str
    author: str | None = None
    tags: list[str]
    step_count: int
    path: str


class PresetListDTO(BaseModel):
    presets: list[PresetDTO]


class PresetValidateDTO(BaseModel):
    path: str
    valid: bool
    errors: list[str]
    warnings: list[str]
    step_count: int = 0


class PlanStepDTO(BaseModel):
    id: str
    type: str
    action: str | None = None
    needs: list[str]
    status: str  # ready | needs_input | not_applicable | blocked
    missing_inputs: list[str]
    reasons: list[str]


class PresetPlanDTO(BaseModel):
    preset_id: str
    name: str
    version: str
    dry_run: bool = True
    steps: list[PlanStepDTO]
    input_requests: list[str]  # preset-level inputs required but without defaults


class PresetRunDTO(BaseModel):
    preset_id: str
    execution_id: str
    status: str
    steps_completed: int


class PresetService(_BaseService):
    def __init__(
        self,
        *,
        registry: Registry,
        presets_dirs: builtins.list[Path],
        engine: PresetEngine | None = None,
        session_scope: Callable[[], AbstractContextManager[object | None]] = nullcontext,
        scope_repo: object = None,
        engagement_repo: object = None,
        artifact_repo: object = None,
    ) -> None:
        super().__init__(
            session_scope=session_scope,
            scope_repo=scope_repo,
            engagement_repo=engagement_repo,
            artifact_repo=artifact_repo,
        )
        self._registry = registry
        self._presets_dirs = presets_dirs
        self._engine = engine

    # ------------------------------------------------------------------ list

    def list(self) -> PresetListDTO:
        found: dict[str, PresetDTO] = {}
        for directory in self._presets_dirs:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml")):
                try:
                    definition = self._load_definition(path)
                except (OSError, yaml.YAMLError, ValidationError):
                    continue  # list only reports loadable presets
                found[definition.metadata.id] = PresetDTO(
                    id=definition.metadata.id,
                    name=definition.metadata.name,
                    version=definition.metadata.version,
                    description=definition.metadata.description,
                    author=definition.metadata.author,
                    tags=list(definition.metadata.tags),
                    step_count=len(definition.steps),
                    path=str(path),
                )
        return PresetListDTO(presets=[found[key] for key in sorted(found)])

    # ------------------------------------------------------------------ validate

    def validate(self, path: str) -> PresetValidateDTO:
        path_obj = Path(path)
        definition = self._load_definition(path_obj)
        errors: builtins.list[str] = []
        warnings: builtins.list[str] = []

        step_ids = [step.id for step in definition.steps]
        if len(step_ids) != len(set(step_ids)):
            dups = {sid for sid in step_ids if step_ids.count(sid) > 1}
            errors.append(f"duplicate step ids: {sorted(dups)}")

        self._check_cycles(definition.steps, errors)

        for step in definition.steps:
            if step.type == "action" and step.action is not None:
                if self._registry.get(step.action) is None:
                    errors.append(f"step {step.id!r}: action {step.action!r} is not registered")
                else:
                    warnings.extend(self._validate_step_bindings(step))
            for value in step.inputs.values():
                self._check_references(value, f"step {step.id!r} inputs", errors)

        for name, binding in definition.outputs.items():
            self._check_references(binding.source, f"output {name!r}", errors)

        return PresetValidateDTO(
            path=str(path_obj),
            valid=not errors,
            errors=errors,
            warnings=warnings,
            step_count=len(definition.steps),
        )

    # ------------------------------------------------------------------ plan

    def plan(self, preset_id: str) -> PresetPlanDTO:
        definition, path = self._find_preset(preset_id)
        validation = self.validate(str(path))
        if not validation.valid:
            raise ValidationError(  # noqa: TRY003 - operator-facing message
                f"preset {preset_id!r} is invalid: " + "; ".join(validation.errors)
            )

        ordered = self._topological_order(definition.steps)
        input_requests = sorted(
            name
            for name, inp in definition.inputs.items()
            if inp.required and inp.default is None
        )

        steps: builtins.list[PlanStepDTO] = [
            self._plan_step(step, definition) for step in ordered
        ]

        return PresetPlanDTO(
            preset_id=definition.metadata.id,
            name=definition.metadata.name,
            version=definition.metadata.version,
            dry_run=True,
            steps=steps,
            input_requests=input_requests,
        )

    # ------------------------------------------------------------------ run

    async def run(
        self,
        preset_id: str,
        *,
        engagement_id: str,
        inputs: dict[str, object] | None = None,
    ) -> PresetRunDTO:
        """Validate, policy-check, and run a preset through the engine."""
        definition, path = self._find_preset(preset_id)
        validation = self.validate(str(path))
        if not validation.valid:
            raise ValidationError(  # noqa: TRY003 - operator-facing message
                f"preset {preset_id!r} is invalid: " + "; ".join(validation.errors)
            )

        with self._session() as session:
            engagement_repo = cast(  # noqa: TC001
                "EngagementRepositoryProtocol",
                self._repo("engagement_repo", session),
            )
            if engagement_repo.get(engagement_id) is None:
                raise NotFoundError(  # noqa: TRY003 - operator-facing identifier
                    f"engagement {engagement_id!r} not found"
                )
            # Touch the scope so a missing scope surfaces as a policy error
            # during execution rather than silently later.
            cast(  # noqa: TC001
                "ScopeRepositoryProtocol",
                self._repo("scope_repo", session),
            ).get_for_engagement(engagement_id)

        # Policy is enforced for every action step before execution so the CLI
        # cannot bypass policy validation.
        from ambrosia.application.policy_gateway import PolicyGateway

        gateway = PolicyGateway(
            session_scope=self._session_scope,
            registry=self._registry,
            engagement_repository=cast(  # noqa: TC001
                "EngagementRepositoryProtocol", self._repos.get("engagement_repo")
            ),
            scope_repository=cast(  # noqa: TC001
                "ScopeRepositoryProtocol", self._repos.get("scope_repo")
            ),
            artifact_repository=cast(  # noqa: TC001
                "ArtifactRepositoryProtocol", self._repos.get("artifact_repo")
            ),
        )
        for step in definition.steps:
            if step.type == "action" and step.action is not None:
                gateway.check_action(
                    action_id=step.action,
                    engagement_id=engagement_id,
                    target_address=None,
                    available_tools=frozenset(),
                )

        if self._engine is None:
            from ambrosia.domain.errors import MissingDependencyError

            raise MissingDependencyError(  # noqa: TRY003 - operator-facing message
                "execution engine (ambrosia.engine) is not integrated yet; "
                "use 'preset plan' for a dry-run plan",
                details={"preset_id": preset_id},
            )

        engine = self._engine
        if engine is None:  # pragma: no cover - guarded above
            from ambrosia.domain.errors import MissingDependencyError

            raise MissingDependencyError(  # noqa: TRY003 - operator-facing message
                "execution engine (ambrosia.engine) is not integrated yet",
                details={"preset_id": preset_id},
            )
        execution_id = str(uuid.uuid4())
        record = await engine.run(
            preset_id=preset_id, execution_id=execution_id, inputs=inputs or {}
        )
        if not isinstance(record, ExecutionRecord):
            record = ExecutionRecord(
                id=execution_id,
                engagement_id=engagement_id,
                preset_id=preset_id,
                status=str(getattr(record, "status", "succeeded")),
            )
        return PresetRunDTO(
            preset_id=preset_id,
            execution_id=record.id,
            status=record.status,
            steps_completed=len(definition.steps),
        )

    # ------------------------------------------------------------------ internals

    def _load_definition(self, path: Path) -> PresetDefinition:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise NotFoundError(  # noqa: TRY003 - operator-facing message
                f"preset file not found: {path}"
            ) from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValidationError(  # noqa: TRY003 - operator-facing message
                f"preset {path} is not valid YAML: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise ValidationError(  # noqa: TRY003 - operator-facing message
                f"preset {path} must contain a mapping, not {type(data).__name__}"
            )
        return PresetDefinition.model_validate(data)

    def _find_preset(self, preset_id: str) -> tuple[PresetDefinition, Path]:
        last_error: str | None = None
        for directory in self._presets_dirs:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml")):
                try:
                    definition = self._load_definition(path)
                except (OSError, yaml.YAMLError, ValidationError) as exc:
                    last_error = str(exc)
                    continue
                if definition.metadata.id == preset_id:
                    return definition, path
        detail = f" ({last_error})" if last_error else ""
        raise NotFoundError(  # noqa: TRY003 - operator-facing message
            f"preset {preset_id!r} not found{detail}"
        )

    @staticmethod
    def _check_cycles(
        steps: builtins.list[PresetStep], errors: builtins.list[str]
    ) -> None:
        by_id = {step.id: step for step in steps}
        visited: set[str] = set()
        stack: set[str] = set()

        def visit(step_id: str, path: builtins.list[str]) -> None:
            if step_id in stack:
                cycle = " -> ".join(path + [step_id])
                errors.append(f"cyclic step dependencies: {cycle}")
                return
            if step_id in visited or step_id not in by_id:
                return
            stack.add(step_id)
            for dep in by_id[step_id].needs:
                visit(dep, path + [step_id])
            stack.discard(step_id)
            visited.add(step_id)

        for step in steps:
            visit(step.id, [])

    @staticmethod
    def _topological_order(
        steps: builtins.list[PresetStep],
    ) -> builtins.list[PresetStep]:
        by_id = {step.id: step for step in steps}
        remaining: set[str] = {step.id for step in steps}
        satisfied: set[str] = set()
        order: builtins.list[PresetStep] = []
        while remaining:
            ready = sorted(
                sid
                for sid in remaining
                if all(dep in satisfied for dep in by_id[sid].needs)
            )
            if not ready:
                break  # cycles were already rejected by validation
            sid = ready[0]
            order.append(by_id[sid])
            satisfied.add(sid)
            remaining.discard(sid)
        return order

    def _plan_step(self, step: PresetStep, definition: PresetDefinition) -> PlanStepDTO:
        step_ids = {s.id for s in definition.steps}
        reasons: builtins.list[str] = []
        status = "ready"
        missing_inputs: builtins.list[str] = []

        unknown_needs = [dep for dep in step.needs if dep not in step_ids]
        if unknown_needs:
            status = "blocked"
            reasons.append(f"unknown dependency step(s): {unknown_needs}")

        if step.type == "action":
            if step.action is not None and self._registry.get(step.action) is None:
                status = "not_applicable"
                reasons.append(f"action {step.action!r} is not registered")
            else:
                required = self._action_required_fields(step)
                for field in required:
                    if field not in step.inputs:
                        missing_inputs.append(field)
                for name, value in step.inputs.items():
                    if self._has_reference(value):
                        missing_inputs.append(name)
                if missing_inputs:
                    status = "needs_input"
                    reasons.append(f"missing input(s): {sorted(set(missing_inputs))}")
        elif step.type == "approval":
            status = "needs_input"
            reasons.append("approval checkpoint requires operator decision")
        else:
            reasons.append(f"step type {step.type!r} planned")

        return PlanStepDTO(
            id=step.id,
            type=step.type,
            action=step.action,
            needs=list(step.needs),
            status=status,
            missing_inputs=sorted(set(missing_inputs)),
            reasons=reasons,
        )

    def _action_required_fields(self, step: PresetStep) -> builtins.list[str]:
        if step.action is None:
            return []
        definition = self._registry.get(step.action)
        if definition is None:
            return []
        schema = definition.input_schema or {}
        raw_required = schema.get("required", []) if isinstance(schema, dict) else []
        if not isinstance(raw_required, list):
            raw_required = []
        return [str(field) for field in raw_required]

    @staticmethod
    def _validate_step_bindings(
        step: PresetStep,
    ) -> builtins.list[str]:
        warnings: builtins.list[str] = []
        for name, value in step.inputs.items():
            if isinstance(value, str):
                warnings.extend(
                    PresetService._reference_warnings(value, f"step {step.id!r} input {name!r}")
                )
        return warnings

    @staticmethod
    def _reference_warnings(value: str, where: str) -> builtins.list[str]:
        warnings: builtins.list[str] = []
        for match in _REFERENCE_RE.finditer(value):
            expression = match.group(1).strip()
            namespace = expression.split(".", 1)[0] if expression else ""
            if namespace not in _VALID_NAMESPACES:
                warnings.append(f"{where}: unknown reference namespace {namespace!r} in {expression!r}")
        return warnings

    @staticmethod
    def _check_references(value: object, where: str, errors: builtins.list[str]) -> None:
        if isinstance(value, str):
            for match in _REFERENCE_RE.finditer(value):
                expression = match.group(1).strip()
                namespace = expression.split(".", 1)[0] if expression else ""
                if namespace not in _VALID_NAMESPACES:
                    errors.append(f"{where}: unknown reference namespace {namespace!r} in {expression!r}")
        elif isinstance(value, dict):
            for key, val in value.items():
                PresetService._check_references(val, f"{where}[{key!r}]", errors)
        elif isinstance(value, list):
            for index, val in enumerate(value):
                PresetService._check_references(val, f"{where}[{index}]", errors)

    @staticmethod
    def _has_reference(value: object) -> bool:
        if isinstance(value, str):
            return bool(_REFERENCE_RE.search(value))
        if isinstance(value, dict):
            return any(PresetService._has_reference(v) for v in value.values())
        if isinstance(value, list):
            return any(PresetService._has_reference(v) for v in value)
        return False


__all__ = [
    "PresetDTO",
    "PresetListDTO",
    "PresetValidateDTO",
    "PlanStepDTO",
    "PresetPlanDTO",
    "PresetRunDTO",
    "PresetService",
]
