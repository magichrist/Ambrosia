"""Ambrosia TUI application: the persistent adaptive workspace shell.

Layout
------
* status bar (docked top): Ambrosia, engagement, scope, target, running jobs
* context rail (left): selected target, targets, last action
* main content area: context-relevant views (dashboard, details, jobs, ...)
* activity / timeline panel (right): recent actions, execution events
* command palette (modal screen): global search triggered with ``/``

The application calls application services (and the job engine) for all
behaviour. It never performs business logic, queries SQLAlchemy directly, or
launches subprocesses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Footer, ListView

from ambrosia.tui.services import (
    ApprovalRequired,
    ExecutionEvent,
    ExecutionFinished,
    ExecutionStarted,
    TUIServiceAdapter,
)
from ambrosia.tui.views.action_details import ActionDetailsView
from ambrosia.tui.views.artifact_browser import ArtifactBrowserView
from ambrosia.tui.views.dashboard import DashboardView
from ambrosia.tui.views.engagement_list import EngagementListView
from ambrosia.tui.views.findings import FindingsView
from ambrosia.tui.views.job_monitor import JobMonitorView
from ambrosia.tui.views.preset_browser import PresetBrowserView
from ambrosia.tui.views.target_scope import TargetScopeView
from ambrosia.tui.widgets.action_list import ActionList
from ambrosia.tui.widgets.activity_panel import ActivityPanel
from ambrosia.tui.widgets.command_palette import CommandPalette
from ambrosia.tui.widgets.context_rail import ContextRail
from ambrosia.tui.widgets.modals import ConfirmDialog, DetailModal, HelpModal
from ambrosia.tui.widgets.status_bar import StatusBar

if TYPE_CHECKING:
    from ambrosia.tui.views.base import BaseView

VIEW_DASHBOARD = "dashboard"
VIEW_ENGAGEMENTS = "engagements"
VIEW_TARGET_SCOPE = "target_scope"
VIEW_JOBS = "jobs"
VIEW_ARTIFACTS = "artifacts"
VIEW_FINDINGS = "findings"
VIEW_PRESETS = "presets"
VIEW_ACTION_DETAILS = "action_details"


class AmbrosiaApp(App[None]):
    """The Ambrosia adaptive workspace."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #status-bar {
        dock: top;
        height: 3;
        padding: 0 1;
    }
    Horizontal#shell {
        height: 1fr;
    }
    #context-rail {
        width: 44;
    }
    #main {
        width: 1fr;
    }
    #activity-panel {
        width: 48;
    }
    Footer {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("/", "action_search", "Search", show=True),
        Binding("tab", "action_focus_next", "Next region", show=True),
        Binding("enter", "action_open", "Open / select", show=True),
        Binding("escape", "action_go_back", "Back / close", show=True),
        Binding("g", "action_engagement_switcher", "Engagement", show=True),
        Binding("?", "action_help", "Help", show=True),
        Binding("q", "action_quit_app", "Quit", show=True),
    ]

    current_engagement_id: reactive[str] = reactive("")
    current_target_address: reactive[str] = reactive("")
    status_text: reactive[str] = reactive("")
    running_jobs: reactive[int] = reactive(0)
    active_view: reactive[str] = reactive(VIEW_ENGAGEMENTS)

    def __init__(self, services: TUIServiceAdapter) -> None:
        super().__init__()
        self._services = services
        self._views: dict[str, BaseView] = {}
        self._view_stack: list[str] = []
        self._status_message = ""

    # ------------------------------------------------------------------ compose

    def compose(self) -> ComposeResult:
        yield StatusBar(id="status-bar")
        yield Horizontal(
            ContextRail(services=self._services, id="context-rail"),
            Horizontal(id="main"),
            ActivityPanel(services=self._services, id="activity-panel"),
            id="shell",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.status_bar().set_status("ready")
        self.show_view(VIEW_ENGAGEMENTS)

    # ------------------------------------------------------------------ reactive watchers

    def watch_current_engagement_id(self, engagement_id: str) -> None:
        self.status_bar().set_engagement(
            self._engagement_name(engagement_id) or engagement_id, engagement_id
        )
        try:
            scope = self._services.show_scope(engagement_id) if engagement_id else None
        except Exception:  # pragma: no cover - defensive
            scope = None
        if scope is not None:
            self.status_bar().set_scope(
                len(scope.include_hosts), len(scope.include_cidrs), len(scope.include_domains)
            )
        self._context_rail().refresh_context()
        self._activity().add_entry(f"[context] engagement {engagement_id or '(none)'}")
        self.refresh_active_view()

    def watch_current_target_address(self, address: str | None) -> None:
        self.status_bar().set_target(address)
        self._context_rail().refresh_context()
        self._activity().add_entry(f"[context] target {address or '(none)'}")
        self.refresh_active_view()

    def watch_running_jobs(self, count: int) -> None:
        self.status_bar().set_running_jobs(count)
        self._activity().add_entry(f"[jobs] running jobs now {count}")

    def watch_active_view(self, name: str) -> None:
        self.refresh_active_view()

    # ------------------------------------------------------------------ helpers

    def status_bar(self) -> StatusBar:
        return self.query_one("#status-bar", StatusBar)

    def _activity(self) -> ActivityPanel:
        return self.query_one("#activity-panel", ActivityPanel)

    def _context_rail(self) -> ContextRail:
        return self.query_one("#context-rail", ContextRail)

    def _main(self) -> Horizontal:
        return self.query_one("#main", Horizontal)

    def _engagement_name(self, engagement_id: str) -> str | None:
        try:
            engagement = self._services.get_engagement(engagement_id)
            return engagement.name
        except Exception:  # pragma: no cover - defensive
            return None

    def current_view(self) -> BaseView | None:
        main = self._main()
        if not main.children:
            return None
        return main.children[0]  # type: ignore[return-value]

    def refresh_active_view(self) -> None:
        view = self.current_view()
        if view is None:
            return
        try:
            view.refresh_view()
        except Exception:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------ navigation

    def show_view(self, name: str, action_id: str | None = None) -> None:
        """Mount (or reuse) the named view in the main content area."""
        main = self._main()
        if main.children:
            main.children[0].remove()
        view: BaseView
        if name == VIEW_ACTION_DETAILS and action_id is not None:
            view = ActionDetailsView(self._services, action_id, id="current-view")
        else:
            cached = self._views.get(name)
            if cached is None:
                cached = self._create_view(name)
                self._views[name] = cached
            view = cached
            view.id = "current-view"
        main.mount(view)
        self.active_view = name
        self._view_stack = [v for v in self._view_stack if v != name]
        self._view_stack.append(name)
        view.refresh_view()
        self._activity().add_entry(f"[view] {name}")

    def _create_view(self, name: str) -> BaseView:
        if name == VIEW_DASHBOARD:
            return DashboardView(self._services, id="current-view")
        if name == VIEW_ENGAGEMENTS:
            return EngagementListView(self._services, id="current-view")
        if name == VIEW_TARGET_SCOPE:
            return TargetScopeView(self._services, id="current-view")
        if name == VIEW_JOBS:
            return JobMonitorView(self._services, id="current-view")
        if name == VIEW_ARTIFACTS:
            return ArtifactBrowserView(self._services, id="current-view")
        if name == VIEW_FINDINGS:
            return FindingsView(self._services, id="current-view")
        if name == VIEW_PRESETS:
            return PresetBrowserView(self._services, id="current-view")
        return DashboardView(self._services, id="current-view")

    def open_action(self, action_id: str) -> None:
        self.show_view(VIEW_ACTION_DETAILS, action_id=action_id)

    # ------------------------------------------------------------------ execution

    def execute_action(
        self,
        action_id: str,
        inputs: dict[str, object] | None = None,
    ) -> None:
        """Run an action in a background worker so the UI stays responsive."""
        self.run_worker(
            self._execute_action_worker(action_id, inputs),
            name=f"run-{action_id}",
        )

    async def _execute_action_worker(
        self,
        action_id: str,
        inputs: dict[str, object] | None = None,
    ) -> None:
        engagement_id = self.current_engagement_id
        target_address = self.current_target_address
        try:
            async for raw_update in self._services.run_action(
                action_id,
                engagement_id=engagement_id,
                target_address=target_address,
                inputs=inputs,
            ):
                update: dict[str, object] = raw_update
                kind = str(update["kind"])
                execution_id = str(update.get("execution_id", ""))
                if kind == "started":
                    self.running_jobs += 1
                    self.status_bar().set_status(f"running {action_id}")
                    self._activity().add_entry(f"[run] {action_id} started ({execution_id[:8]})")
                    self.post_message(ExecutionStarted(execution_id))
                elif kind == "event":
                    self._activity().add_entry(
                        f"[event] {update.get('event_kind')} {str(update.get('payload', {}))[:120]}"
                    )
                    payload = update.get("payload")
                    payload_dict = payload if isinstance(payload, dict) else {}
                    self.post_message(
                        ExecutionEvent(
                            execution_id,
                            str(update.get("event_kind", "")),
                            dict(payload_dict),
                        )
                    )
                elif kind == "approval_required":
                    self._activity().add_entry(
                        f"[approval] awaiting decision ({str(update.get('approval_id', ''))[:8]})"
                    )
                    self.post_message(
                        ApprovalRequired(execution_id, str(update.get("approval_id", "")))
                    )
                elif kind == "finished":
                    self.running_jobs = max(0, self.running_jobs - 1)
                    status = str(update.get("status", "unknown"))
                    self.status_bar().set_status(f"{action_id} -> {status}")
                    self._activity().add_entry(
                        f"[done] {action_id} finished ({execution_id[:8]}) -> {status}"
                    )
                    self.post_message(ExecutionFinished(execution_id, status))
                    # Refresh suggestions in place; never dump back to a menu.
                    self.refresh_active_view()
        except Exception as exc:  # pragma: no cover - surfaced to operator
            self.running_jobs = max(0, self.running_jobs - 1)
            self.status_bar().set_status(f"error: {exc}")
            self._activity().add_entry(f"[error] {action_id}: {exc}")
            self.post_message(ExecutionFinished("", "failed"))

    def parse_inputs(self, raw: str | None) -> dict[str, object]:
        """Parse a ``key=value,key2=value2`` string into typed inputs."""
        inputs: dict[str, object] = {}
        if not raw:
            return inputs
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            inputs[key.strip()] = value.strip()
        return inputs

    # ------------------------------------------------------------------ action handlers (bindings)

    def action_search(self) -> None:
        self.push_screen(CommandPalette(self._services), self._handle_palette_result)

    def _handle_palette_result(self, result: dict[str, object] | None) -> None:
        if result is None:
            return
        if result.get("kind") == "action":
            self.open_action(str(result["id"]))

    def action_open(self) -> None:
        focused = self.focused
        if focused is None:
            return
        # Action list (dashboard): open the selected action's details.
        if isinstance(focused, ActionList):
            action_id = focused.selected_action_id()
            if action_id is not None:
                self.open_action(action_id)
            return
        # List views: route by widget id.
        if isinstance(focused, ListView):
            list_id = focused.id or ""
            highlighted = focused.highlighted_child
            if highlighted is None or highlighted.id is None:
                return
            item_id = highlighted.id
            if list_id == "engagements-list":
                self.current_engagement_id = item_id
                self.show_view(VIEW_DASHBOARD)
            elif list_id == "jobs-list":
                self._show_job_detail(item_id)
            elif list_id == "artifacts-list":
                self._show_artifact_detail(item_id)
            elif list_id == "findings-list":
                self._show_finding_detail(item_id)

    def _show_job_detail(self, job_id: str) -> None:
        try:
            show = self._services.job_show(job_id)
        except Exception:  # pragma: no cover - defensive
            return
        lines = [
            f"id: {show.job.id}",
            f"status: {show.job.status}",
            f"action: {show.job.action_id or show.job.preset_id or '-'}",
            f"targets: {', '.join(show.job.target_refs) or '(none)'}",
            f"started: {show.job.started_at or '-'}",
            f"finished: {show.job.finished_at or '-'}",
        ]
        if show.job.error_code:
            lines.append(f"error_code: {show.job.error_code}")
            lines.append(f"error_message: {show.job.error_message}")
        lines.append("")
        lines.append("events:")
        for event in show.events:
            lines.append(f"  [{event.sequence}] {event.kind} {event.timestamp or ''}")
        self.push_screen(DetailModal(f"Job {job_id[:8]}", "\n".join(lines)))

    def _show_artifact_detail(self, artifact_id: str) -> None:
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        for artifact in self._services.list_artifacts(engagement_id):
            if artifact.id == artifact_id:
                lines = [
                    f"id: {artifact.id}",
                    f"type: {artifact.type}",
                    f"target_ref: {artifact.target_ref or '(none)'}",
                    f"source_kind: {artifact.source_kind}",
                    f"source_id: {artifact.source_id or '(none)'}",
                    f"created_at: {artifact.created_at.isoformat()}",
                    f"sensitivity: {artifact.sensitivity}",
                    f"secret_ref: {artifact.secret_ref or '(none)'}",
                    f"confidence: {artifact.confidence}",
                ]
                lines.append("")
                lines.append("value:")
                for key, val in (artifact.value or {}).items():
                    lines.append(f"  {key}: {val}")
                self.push_screen(DetailModal(f"Artifact {artifact.id[:8]}", "\n".join(lines)))
                return

    def _show_finding_detail(self, finding_id: str) -> None:
        app = self.app  # set by Textual at mount
        engagement_id = getattr(app, "current_engagement_id", "") or ""
        for finding in self._services.list_findings(engagement_id):
            if finding.id == finding_id:
                lines = [
                    f"id: {finding.id}",
                    f"type: {finding.type}",
                    f"target_ref: {finding.target_ref or '(none)'}",
                    f"source_kind: {finding.source_kind}",
                    f"created_at: {finding.created_at.isoformat()}",
                ]
                lines.append("")
                lines.append("value:")
                for key, val in (finding.value or {}).items():
                    lines.append(f"  {key}: {val}")
                self.push_screen(DetailModal(f"Finding {finding.id[:8]}", "\n".join(lines)))
                return

    def action_go_back(self) -> None:
        if len(self.screen_stack) > 1:
            self.pop_screen()
            return
        if len(self._view_stack) > 1:
            self._view_stack.pop()
            self.show_view(self._view_stack[-1])
        else:
            self.show_view(VIEW_DASHBOARD)

    def action_engagement_switcher(self) -> None:
        self.show_view(VIEW_ENGAGEMENTS)

    def action_help(self) -> None:
        self.push_screen(HelpModal())

    def action_quit_app(self) -> None:
        if self.running_jobs > 0:
            self.push_screen(
                ConfirmDialog(
                    "Jobs are still running. Quit anyway?",
                    confirm_label="Quit",
                ),
                self._handle_quit_confirm,
            )
            return
        self.exit()

    def _handle_quit_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self.exit()

    # ------------------------------------------------------------------ message handlers

    def _on_execution_started(self, message: ExecutionStarted) -> None:
        self._activity().add_entry(f"[execution] {message.execution_id[:8]} started")

    def _on_execution_event(self, message: ExecutionEvent) -> None:
        pass  # events already logged to the activity panel by the worker

    def _on_execution_finished(self, message: ExecutionFinished) -> None:
        self._activity().add_entry(f"[execution] {message.execution_id[:8]} -> {message.status}")

    def _on_approval_required(self, message: ApprovalRequired) -> None:
        self.status_bar().set_status("awaiting approval")
        self.push_screen(
            ConfirmDialog(
                "Execution requires approval. Grant it?",
                confirm_label="Grant",
            ),
            lambda confirmed: self._handle_approval(confirmed, message),
        )

    async def _handle_approval(self, confirmed: bool | None, message: ApprovalRequired) -> None:
        if not confirmed:
            await self._services.deny_approval(message.execution_id, message.approval_id)
            self.status_bar().set_status("execution denied")
            self.refresh_active_view()
            return
        await self._services.grant_approval(message.execution_id, message.approval_id)
        self.status_bar().set_status("approved — run again to execute")
        self.refresh_active_view()


__all__ = ["AmbrosiaApp", "build_app"]


def build_app(services: TUIServiceAdapter) -> AmbrosiaApp:
    """Build the TUI application around an (already wired) service adapter."""
    return AmbrosiaApp(services)
