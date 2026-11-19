"""Context rail widget: selected target, targets, last action."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from ambrosia.tui.services import TUIServiceAdapter


class ContextRail(Static):
    """Left sidebar summarising the current engagement context."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(id=id)
        self._services = services

    # ------------------------------------------------------------------ render

    def render(self) -> str:
        app = self.app  # set by Textual at mount
        lines: list[str] = []
        lines.append("context rail")
        lines.append("=" * 14)
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        if engagement_id:
            try:
                engagement = self._services.get_engagement(engagement_id)
                lines.append(f"engagement: {engagement.name}")
            except Exception:  # pragma: no cover - defensive display fallback
                lines.append(f"engagement: {engagement_id}")
            try:
                targets = self._services.list_targets(engagement_id)
                if targets.targets:
                    lines.append("targets:")
                    for target in targets.targets:
                        lines.append(f"  * {target.address} ({target.kind})")
                else:
                    lines.append("targets: (none)")
            except Exception:  # pragma: no cover - defensive display fallback
                lines.append("targets: (error)")
        else:
            lines.append("engagement: (none selected)")
        lines.append("")
        lines.append("actions: use / to search, Enter to open")
        lines.append("g: switch engagement   q: quit")
        return "\n".join(lines)

    def refresh_context(self) -> None:
        self.refresh()


__all__ = ["ContextRail"]
