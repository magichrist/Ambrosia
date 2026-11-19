"""Status bar widget: Ambrosia branding, engagement, scope, target, jobs."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    """Top status bar showing the current workspace context."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._engagement = "no engagement"
        self._engagement_id = ""
        self._scope = "no scope"
        self._target = "no target"
        self._running_jobs = 0
        self._status = ""

    # ------------------------------------------------------------------ updates

    def set_engagement(self, name: str, engagement_id: str) -> None:
        self._engagement = name
        self._engagement_id = engagement_id
        self.refresh()

    def set_scope(self, include_hosts: int, include_cidrs: int, include_domains: int) -> None:
        parts: list[str] = []
        if include_hosts:
            parts.append(f"{include_hosts} host(s)")
        if include_cidrs:
            parts.append(f"{include_cidrs} cidr(s)")
        if include_domains:
            parts.append(f"{include_domains} domain(s)")
        self._scope = ", ".join(parts) if parts else "empty (nothing authorized)"
        self.refresh()

    def set_target(self, address: str | None) -> None:
        self._target = address or "none"
        self.refresh()

    def set_running_jobs(self, count: int) -> None:
        self._running_jobs = count
        self.refresh()

    def set_status(self, message: str) -> None:
        self._status = message
        self.refresh()

    # ------------------------------------------------------------------ render

    def render(self) -> Text:
        text = Text()
        text.append("Ambrosia", style="bold #00ff88")
        text.append("  |  ", style="dim")
        text.append("engagement: ", style="dim")
        text.append(self._engagement, style="bold")
        text.append(f" ({self._engagement_id[:8]})" if self._engagement_id else "", style="dim")
        text.append("  |  ", style="dim")
        text.append("scope: ", style="dim")
        text.append(self._scope, style="#ffd066")
        text.append("  |  ", style="dim")
        text.append("target: ", style="dim")
        text.append(self._target, style="#7fbfff")
        text.append("  |  ", style="dim")
        jobs = self._running_jobs
        text.append("jobs: ", style="dim")
        text.append(str(jobs), style="bold #ff6666" if jobs else "#00ff88")
        if self._status:
            text.append("  |  ", style="dim")
            text.append(self._status, style="italic #cccccc")
        return text


__all__ = ["StatusBar"]
