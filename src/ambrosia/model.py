"""v2 command model.

The command is the unit of work in Ambrosia v2. A :class:`Command` is a plain
frozen record describing a shell command template with named
:class:`CommandInput` instances. Input value resolution and shell templating
(``{{input_id}}`` substitution) are handled by the executor, not here; this
module only knows the record shape and JSON round-tripping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True)
class CommandInput:
    """A single named input for a :class:`Command`.

    ``type`` is a hint only (``host``, ``string``, ``path``, ``integer``,
    ``secret``) and is not enforced here. ``secret`` inputs are masked in the
    TUI and are not persisted by default.
    """

    id: str
    prompt: str
    type: str = "string"
    required: bool = True
    secret: bool = False
    default: str | None = None
    validation_hint: str = ""

    def to_dict(self) -> dict[str, str | bool | None]:
        """Serialize this input to a JSON-friendly dict."""
        return {
            "id": self.id,
            "prompt": self.prompt,
            "type": self.type,
            "required": self.required,
            "secret": self.secret,
            "default": self.default,
            "validation_hint": self.validation_hint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        """Deserialize an input from a JSON dict, tolerating missing keys."""
        default_raw = data.get("default")
        default: str | None = str(default_raw) if default_raw is not None else None
        return cls(
            id=str(data["id"]),
            prompt=str(data["prompt"]),
            type=str(data.get("type", "string")),
            required=bool(data.get("required", True)),
            secret=bool(data.get("secret", False)),
            default=default,
            validation_hint=str(data.get("validation_hint", "")),
        )


@dataclass(frozen=True)
class Command:
    """A single runnable command: name, description, tags, shell template, inputs.

    ``shell`` is a template with ``{{input_id}}`` placeholders that the
    executor substitutes at run time. This class does not perform substitution;
    only complete ``{{...}}`` tokens are recognized by the executor.
    """

    id: str
    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    shell: str = ""
    inputs: list[CommandInput] = field(default_factory=list)
    category: str = ""
    favorite: bool = False
    pinned: bool = False

    def input_by_id(self, input_id: str) -> CommandInput | None:
        """Return the input with ``input_id``, or ``None`` if not present."""
        for input_ in self.inputs:
            if input_.id == input_id:
                return input_
        return None

    def required_inputs(self) -> list[CommandInput]:
        """Return inputs marked required, in declaration order."""
        return [input_ for input_ in self.inputs if input_.required]

    def all_inputs_filled(self, values: dict[str, str]) -> bool:
        """Return True if every required input has a non-empty value in ``values``."""
        return all(bool(values.get(input_.id, "")) for input_ in self.required_inputs())

    def to_dict(self) -> dict[str, object]:
        """Serialize this command to a JSON-friendly dict."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "shell": self.shell,
            "inputs": [input_.to_dict() for input_ in self.inputs],
            "category": self.category,
            "favorite": self.favorite,
            "pinned": self.pinned,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Self:
        """Deserialize a command from a JSON dict, tolerating missing keys."""
        tags_raw = data.get("tags", [])
        tags: list[str] = [str(tag) for tag in tags_raw] if isinstance(tags_raw, list) else []

        inputs_raw = data.get("inputs", [])
        inputs: list[CommandInput] = []
        if isinstance(inputs_raw, list):
            for item in inputs_raw:
                if isinstance(item, dict):
                    inputs.append(CommandInput.from_dict(item))

        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            description=str(data["description"]),
            tags=tags,
            shell=str(data.get("shell", "")),
            inputs=inputs,
            category=str(data.get("category", "")),
            favorite=bool(data.get("favorite", False)),
            pinned=bool(data.get("pinned", False)),
        )
