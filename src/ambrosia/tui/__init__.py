"""Ambrosia TUI package.

The Textual application lives here and is intentionally self-contained: it
depends only on the :mod:`ambrosia` model, storage, session, and executor
adapters, never on any v1 code.
"""

from ambrosia.tui.app import AmbrosiaApp

__all__ = ["AmbrosiaApp"]
