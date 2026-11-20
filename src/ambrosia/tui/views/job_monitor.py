"""Job monitor view: execution history and live job details."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import Button, Label, ListItem, ListView, Static

from ambrosia.tui.views.base import BaseView

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from ambrosia.application.job_service import JobDTO
    from ambrosia.tui.services import TUIServiceAdapter


class JobMonitorView(BaseView):
    """List executions for the current engagement and show job details/events."""

    def __init__(self, services: TUIServiceAdapter, id: str | None = None) -> None:
        super().__init__(services, id=id)
        self._jobs: list[JobDTO] = []

    def compose(self) -> ComposeResult:
        yield Label("Executions", id="jobs-title")
        yield ListView(id="jobs-list")
        yield Static(id="jobs-body")
        with Vertical():
            yield Button("Refresh", id="refresh-jobs")
            yield Button("Cancel selected", id="cancel-job", variant="error")
            yield Button("Back", id="back-jobs")

    def on_mount(self) -> None:
        # Defer until composed children are available in the DOM.
        self.call_after_refresh(self.safe_refresh)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "refresh-jobs":
            self.call_after_refresh(self.safe_refresh)
        elif button_id == "back-jobs":
            self.workspace.action_go_back()
        elif button_id == "cancel-job":
            job_id = self.selected_job_id()
            if job_id is None:
                self.query_one("#jobs-body", Static).update("Select an execution to cancel.")
                return
            self.workspace.run_worker(
                self.services.cancel_job(job_id), name=f"cancel-{job_id}"
            )
            self.query_one("#jobs-body", Static).update(f"Cancelling {job_id[:8]} ...")
            self.call_after_refresh(self.safe_refresh)

    async def refresh_view(self) -> None:
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        body = self.query_one("#jobs-body", Static)
        job_list = self.query_one("#jobs-list", ListView)
        await job_list.clear()
        self._jobs = []
        if not engagement_id:
            body.update("No engagement selected.")
            return
        try:
            dto = self.services.job_list(engagement_id)
        except Exception as exc:  # pragma: no cover - services unavailable
            body.update(f"Unable to load executions: {exc}")
            return
        self._jobs = list(dto.jobs)
        for job in self._jobs:
            label = f"{job.id[:8]}  {job.status:12}  {job.action_id or job.preset_id or '-'}"
            await job_list.append(ListItem(Static(label), id=job.id))
        if not self._jobs:
            body.update("No executions yet.")
        else:
            body.update(f"{len(self._jobs)} execution(s). Select one and press Enter to inspect.")

    def selected_job_id(self) -> str | None:
        item = self.query_one("#jobs-list", ListView).highlighted_child
        if item is None:
            return None
        return item.id

    def selected_job(self) -> object | None:
        job_id = self.selected_job_id()
        if job_id is None:
            return None
        for job in self._jobs:
            if job.id == job_id:
                return job
        return None


__all__ = ["JobMonitorView"]
