"""Context snapshots, derived facts, and the engagement-scoped context service.

The service queries repositories through protocols and never duplicates every
artifact in a mutable arbitrary dictionary.
"""

from __future__ import annotations

from ambrosia.context.models import ContextSnapshot, Fact
from ambrosia.context.service import ContextService

__all__ = ["ContextSnapshot", "Fact", "ContextService"]
