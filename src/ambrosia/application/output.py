"""Output formatting for CLI commands.

Ambrosia commands render in one of two modes:

* ``human`` — free-form text for operators (default).
* ``json``  — stable, machine-readable JSON for automation.

JSON payloads are produced from Pydantic models via ``model_dump(mode="json")``
so datetimes serialize as ISO-8601 strings and key order is stable
(``sort_keys=True``). Secret values are never included: application services
return DTOs that contain only safe display data.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Literal, cast

from pydantic import BaseModel

from ambrosia.domain.errors import ValidationError

OutputFormat = Literal["human", "json"]


def _jsonable(value: Any) -> Any:
    """Convert a service result to a JSON-serializable structure."""
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return str(value)  # fall back to a string so error details always serialize


def format_json(value: Any) -> str:
    """Serialize ``value`` to stable, indented JSON (trailing newline)."""
    return json.dumps(_jsonable(value), indent=2, sort_keys=True) + "\n"


def parse_human_flag(output: str | None) -> OutputFormat:
    """Normalize a CLI ``--output`` value, defaulting to human-readable."""
    if output is None:
        return "human"
    if output not in ("human", "json"):
        raise ValidationError(  # noqa: TRY003 - operator-facing message includes the invalid value
            f"unsupported --output value: {output!r} (use 'human' or 'json')"
        )
    return cast("OutputFormat", output)


__all__ = ["OutputFormat", "format_json", "parse_human_flag"]
