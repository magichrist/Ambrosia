"""Search parsing, ranking, and regex validation for the workstation explorer.

Queries support optional field qualifiers (``name:``, ``cmd:``, ``tag:``,
``path:``) plus ``type:`` which selects the result kind (``preset`` or
``workflow``). Tokens that are not qualifiers are free text and match across
all searchable fields. Qualifiers and free text are ANDed together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ambrosia.model import Command
from ambrosia.workflow import Workflow

SearchMode = Literal["substring", "fuzzy", "regex"]

_QUALIFIERS = ("name:", "cmd:", "tag:", "path:", "type:", "t:")

# Result kinds accepted by the ``type:`` / ``t:`` qualifier. An empty value
# means "all". Short values let operators type ``t:w`` instead of
# ``type:workflow``.
_RESULT_TYPES = ("preset", "workflow", "all")
_TYPE_ALIASES = {"w": "workflow", "p": "preset", "a": "all"}
_RESULT_TYPE_BY_SHORT = {"t": "type"}


@dataclass
class SearchQuery:
    """A parsed search query."""

    raw: str = ""
    mode: SearchMode = "substring"
    qualifiers: dict[str, str] = field(default_factory=dict)
    free_text: str = ""

    def is_empty(self) -> bool:
        """True when there is nothing to search by."""
        return not self.raw.strip()


@dataclass(frozen=True)
class SearchResult:
    """A result item (preset command or workflow) plus its ranking metadata."""

    item: Command | Workflow
    rank: int
    matched_fields: tuple[str, ...]
    tiebreaker: int = 0

    @property
    def command(self) -> Command | None:
        """The matched command, or ``None`` for a workflow result."""
        return self.item if isinstance(self.item, Command) else None

    @property
    def workflow(self) -> Workflow | None:
        """The matched workflow, or ``None`` for a preset result."""
        return self.item if isinstance(self.item, Workflow) else None


def parse_search_query(raw: str, mode: SearchMode = "substring") -> SearchQuery:
    """Parse raw input into qualifiers and free text."""
    qualifiers: dict[str, str] = {}
    free_parts: list[str] = []
    for token in raw.split():
        for prefix in _QUALIFIERS:
            if token.startswith(prefix):
                key = _RESULT_TYPE_BY_SHORT.get(prefix[:-1], prefix[:-1])
                value = token[len(prefix) :]
                if key == "type":
                    value = value.strip().lower()
                    value = _TYPE_ALIASES.get(value, value)
                qualifiers[key] = value
                break
        else:
            free_parts.append(token)
    return SearchQuery(
        raw=raw,
        mode=mode,
        qualifiers=qualifiers,
        free_text=" ".join(free_parts),
    )


def regex_error(query: SearchQuery) -> str | None:
    """Return a human-readable error for an invalid regex query, or ``None``.

    All regex patterns in the query (free text and qualifier values) are
    compiled so invalid syntax is surfaced instead of silently matching
    nothing.
    """
    patterns = [
        query.free_text,
        *(value for key, value in query.qualifiers.items() if key != "type"),
    ]
    for pattern in patterns:
        if not pattern:
            continue
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"invalid regex {pattern!r}: {exc}"
    return None


def _field_text(command: Command, field_name: str) -> str:
    if field_name == "name":
        return command.name
    if field_name == "cmd":
        return command.shell
    if field_name == "tag":
        return " ".join(command.tags)
    if field_name == "path":
        return command.category
    return ""


def _all_text(command: Command) -> str:
    return " ".join(
        [
            command.name,
            command.shell,
            " ".join(command.tags),
            command.category,
            command.description,
        ]
    )


def _fuzzy_score(query: str, text: str) -> int | None:
    """Return the match span length when ``query`` is a subsequence of ``text``."""
    query = query.lower()
    text = text.lower()
    start: int | None = None
    index = 0
    for char in query:
        found = text.find(char, index)
        if found == -1:
            return None
        if start is None:
            start = found
        index = found + 1
    if start is None:
        return None
    return index - start


def _matches(pattern: str, text: str, mode: SearchMode) -> int | None:
    """Return a match rank (lower is better) or ``None`` when there is no match."""
    if not pattern:
        return 0
    if mode == "regex":
        try:
            match = re.search(pattern, text, re.IGNORECASE)
        except re.error:
            return None
        if match is None:
            return None
        return match.start()
    if mode == "fuzzy":
        return _fuzzy_score(pattern, text)
    position = text.lower().find(pattern.lower())
    if position == -1:
        return None
    # A match at the start of a word ("win" in "windows") is a stronger hit
    # than a match buried inside a word; chunk/partial matches still count.
    at_word_start = position == 0 or not text[position - 1].isalnum()
    return position - 25 if at_word_start else position


def _wanted_type(query: SearchQuery) -> str:
    """Return the normalized ``type:`` filter, or ``""`` when unrestricted."""
    return query.qualifiers.get("type", "").strip().lower()


def _type_allowed(query: SearchQuery, kind: str) -> bool:
    wanted = _wanted_type(query)
    return wanted in ("", "all", kind)


def _has_search_content(query: SearchQuery) -> bool:
    """True when the query asks for anything besides a result-type filter."""
    return bool(query.free_text.strip()) or any(
        key != "type" and value.strip() for key, value in query.qualifiers.items()
    )


def _free_terms(query: SearchQuery) -> list[str]:
    """Return the free-text terms that must all match.

    Substring and fuzzy searches treat each whitespace-separated word as its
    own term, so ``regis rdp`` finds an item that has ``regis`` in one field
    and ``rdp`` in another. Regex mode keeps the whole string as one pattern.
    """
    text = query.free_text.strip()
    if not text:
        return []
    if query.mode == "regex":
        return [text]
    return text.split()


def match_command(command: Command, query: SearchQuery) -> SearchResult | None:
    """Return ranking metadata when ``command`` matches ``query``."""
    if not _type_allowed(query, "preset"):
        return None
    if not _has_search_content(query):
        return SearchResult(item=command, rank=0, matched_fields=())

    fields: tuple[str, ...] = ("name", "cmd", "tag", "path")
    matched: list[str] = []
    ranks: list[int] = []
    for field_name in fields:
        value = query.qualifiers.get(field_name)
        if value is None:
            continue
        score = _matches(value, _field_text(command, field_name), query.mode)
        if score is None:
            return None
        matched.append(field_name)
        ranks.append(score + 10)  # qualifiers outweigh free-text matches

    terms = _free_terms(query)
    if terms:
        # Match each term against every field on its own: all terms must hit
        # somewhere, but different terms may match different fields. Ranking
        # uses each term's best field rather than a concatenated-text blob.
        texts = [
            command.name,
            command.shell,
            " ".join(command.tags),
            command.category,
            command.description,
        ]
        for term in terms:
            scores = [score for text in texts if (score := _matches(term, text, query.mode)) is not None]
            if not scores:
                return None
            if "all" not in matched:
                matched.append("all")
            ranks.append(min(scores))

    if not matched:
        return None
    rank = sum(ranks)
    return SearchResult(
        item=command,
        rank=rank,
        matched_fields=tuple(matched),
        tiebreaker=len(command.name),
    )


def match_workflow(workflow: Workflow, query: SearchQuery) -> SearchResult | None:
    """Return ranking metadata when ``workflow`` matches ``query``."""
    if not _type_allowed(query, "workflow"):
        return None
    if not _has_search_content(query):
        return SearchResult(item=workflow, rank=0, matched_fields=())

    command_ids = workflow.command_ids()
    field_values = {
        "name": workflow.name,
        "cmd": " ".join(command_ids),
        "tag": "",
        "path": workflow.id,
    }
    matched: list[str] = []
    ranks: list[int] = []
    for field_name, value in field_values.items():
        qualifier = query.qualifiers.get(field_name)
        if qualifier is None:
            continue
        score = _matches(qualifier, value, query.mode)
        if score is None:
            return None
        matched.append(field_name)
        ranks.append(score + 10)

    terms = _free_terms(query)
    if terms:
        texts = [
            workflow.name,
            workflow.description,
            workflow.id,
            " ".join(workflow.phase_names()),
            " ".join(command_ids),
        ]
        for term in terms:
            scores = [score for text in texts if (score := _matches(term, text, query.mode)) is not None]
            if not scores:
                return None
            if "all" not in matched:
                matched.append("all")
            ranks.append(min(scores))

    if not matched:
        return None
    return SearchResult(
        item=workflow,
        rank=sum(ranks),
        matched_fields=tuple(matched),
        tiebreaker=len(workflow.name),
    )


def _sort_results(results: list[SearchResult]) -> list[SearchResult]:
    results.sort(key=lambda result: (result.rank, result.tiebreaker, result.item.name.lower()))
    return results


def search_commands(commands: list[Command], query: SearchQuery) -> list[SearchResult]:
    """Return ranked preset matches for ``commands`` against ``query``."""
    results = [
        result
        for command in commands
        if (result := match_command(command, query)) is not None
    ]
    return _sort_results(results)


def search_workflows(workflows: list[Workflow], query: SearchQuery) -> list[SearchResult]:
    """Return ranked workflow matches for ``workflows`` against ``query``."""
    results = [
        result
        for workflow in workflows
        if (result := match_workflow(workflow, query)) is not None
    ]
    return _sort_results(results)


def search_items(
    commands: list[Command], workflows: list[Workflow], query: SearchQuery
) -> list[SearchResult]:
    """Return ranked preset and workflow matches in one list."""
    return _sort_results([*search_commands(commands, query), *search_workflows(workflows, query)])


__all__ = [
    "SearchMode",
    "SearchQuery",
    "SearchResult",
    "match_command",
    "match_workflow",
    "parse_search_query",
    "regex_error",
    "search_commands",
    "search_items",
    "search_workflows",
]
