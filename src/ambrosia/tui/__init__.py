"""Ambrosia adaptive Textual TUI.

The TUI is a presentation layer only. It calls application services (and the
execution engine) for all behaviour; it never performs business logic, queries
SQLAlchemy directly, or launches subprocesses.
"""

from __future__ import annotations

from ambrosia.tui.app import AmbrosiaApp, build_app

__all__ = ["AmbrosiaApp", "build_app"]
