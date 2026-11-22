"""Search parsing, ranking, and regex validation for the preset explorer.

Queries support optional field qualifiers (``name:``, ``cmd:``, ``tag:``,
``path:``). Tokens that are not qualifiers are free text and match across all
four fields. Qualifiers and free text are ANDed together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ambrosia.model import Command

SearchMode = Literal["substring", "fuzzy", "regex"]

_QUALIFIERS = ("name:", "cmd:", "tag:", "path:")


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
    """A command plus its ranking metadata."""

    command: Command
    rank: int
    matched_fields: tuple[str, ...]
    tiebreaker: int = 0


def parse_search_query(raw: str, mode: SearchMode = "substring") -> SearchQuery:
    """Parse raw input into qualifiers and free text."""
    qualifiers: dict[str, str] = {}
    free_parts: list[str] = []
    for token in raw.split():
        for prefix in _QUALIFIERS:
            if token.startswith(prefix):
                qualifiers[prefix[:-1]] = token[len(prefix) :]
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
    patterns = [query.free_text, *query.qualifiers.values()]
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


def match_command(command: Command, query: SearchQuery) -> SearchResult | None:
    """Return ranking metadata when ``command`` matches ``query``."""
    if query.is_empty():
        return SearchResult(command=command, rank=0, matched_fields=())

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

    if query.free_text:
        # Match each field on its own so word/word-fragment hits are ranked by
        # their best field instead of by a position in a concatenated blob.
        texts = [
            command.name,
            command.shell,
            " ".join(command.tags),
            command.category,
            command.description,
        ]
        scores = [
            score for text in texts if (score := _matches(query.free_text, text, query.mode)) is not None
        ]
        if not scores:
            return None
        matched.append("all")
        ranks.append(min(scores))

    if not matched:
        return None
    rank = sum(ranks)
    return SearchResult(
        command=command,
        rank=rank,
        matched_fields=tuple(matched),
        tiebreaker=len(command.name),
    )


def search_commands(commands: list[Command], query: SearchQuery) -> list[SearchResult]:
    """Return ranked matches for ``commands`` against ``query``."""
    results: list[SearchResult] = []
    for command in commands:
        result = match_command(command, query)
        if result is not None:
            results.append(result)
    results.sort(key=lambda result: (result.rank, result.tiebreaker, result.command.name.lower()))
    return results


__all__ = [
    "SearchMode",
    "SearchQuery",
    "SearchResult",
    "match_command",
    "parse_search_query",
    "regex_error",
    "search_commands",
]
