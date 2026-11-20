"""Normalize engine-only step keys shared by the preset loader and services.

The domain :class:`~ambrosia.domain.preset.PresetStep` model is deliberately
strict (``extra="forbid"``). Condition steps in ``ambrosia/v1`` documents use
two extra keys, ``then`` and ``else``, which belong to the engine's branch DAG
rather than to the serialized definition. Both the loader and the application
service must strip them before strict Pydantic validation, so the logic lives
here as a single source of truth.

Genuine typos (e.g. ``actin``) are still rejected by ``extra="forbid"``.
"""

from __future__ import annotations

from typing import Any

from ambrosia.presets.errors import PresetValidationError

# Step id -> (then step ids, else step ids).
BranchMap = dict[str, tuple[tuple[str, ...], tuple[str, ...]]]


def normalize_engine_step_keys(data: dict[str, Any]) -> BranchMap:
    """Pop ``then``/``else`` from each step mapping, in place.

    Mutates ``data["steps"]`` so the remaining step fields strictly conform to
    the domain model. Returns the branch map keyed by step id so callers that
    build an execution plan can restore branch/wiring information.
    """
    branches: BranchMap = {}
    raw_steps = data.get("steps", [])
    if not isinstance(raw_steps, list):
        raise PresetValidationError("'steps' must be a list")  # noqa: TRY003

    normalized: list[dict[str, Any]] = []
    for index, raw_step in enumerate(raw_steps):
        label = f"steps[{index}]"
        if not isinstance(raw_step, dict):
            raise PresetValidationError(f"{label}: step must be a mapping")  # noqa: TRY003
        step = dict(raw_step)
        then = _as_step_ids(step.pop("then", []), f"{label}.then")
        else_ = _as_step_ids(step.pop("else", []), f"{label}.else")
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            raise PresetValidationError(  # noqa: TRY003
                f"{label}: step 'id' must be a non-empty string"
            )
        if then or else_:
            branches[step_id] = (tuple(then), tuple(else_))
        normalized.append(step)

    data["steps"] = normalized
    return branches


def _as_step_ids(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise PresetValidationError(f"{label}: must be a list of step ids")  # noqa: TRY003
    for item in value:
        if not isinstance(item, str):
            raise PresetValidationError(f"{label}: entries must be step id strings")  # noqa: TRY003
    return list(value)


__all__ = ["BranchMap", "normalize_engine_step_keys"]
