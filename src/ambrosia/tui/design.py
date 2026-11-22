"""Shared "Female Cyber Space" palette for the v2 TUI.

Warm amber-charcoal surfaces (the "ALL" button color), rose/magenta accents,
and phosphor-green highlights. No aubergine or cold blue: bright hover
backgrounds always pair with dark foreground text for readability.
"""

from __future__ import annotations

# Panels — warm charcoal, not purple
DARK_PANEL_BG = "#1c1810"
DEEP_PANEL_BG = "#0f0d0a"
SELECTED_BG = "#3a2a0f"
HOVER_BG = "#4a3512"

# Rose / magenta accents
FEMME_PINK = "#ff5fa2"
GUMMY_PINK = "#ff2e88"
GUMMY_LIGHT_PINK = "#ff9ec9"
GUMMY_RED = "#ff5c7a"

# Warm highlights (the ALL button palette)
AMBER = "#ffb454"
YELLOW = "#ffe08a"
PHOSPHOR = "#b6ff5c"
GUMMY_GREEN = PHOSPHOR

# Text — warm cream, not lavender
TEXT_PRIMARY = "#fff4dd"
TEXT_MUTED = "#cdbb95"

# Backwards-compatible aliases used by existing stylesheets.
PHOSPHOR_CYAN = PHOSPHOR
GUMMY_AMBER = AMBER

__all__ = [
    "AMBER",
    "DARK_PANEL_BG",
    "DEEP_PANEL_BG",
    "FEMME_PINK",
    "GUMMY_AMBER",
    "GUMMY_GREEN",
    "GUMMY_LIGHT_PINK",
    "GUMMY_PINK",
    "GUMMY_RED",
    "HOVER_BG",
    "PHOSPHOR",
    "PHOSPHOR_CYAN",
    "SELECTED_BG",
    "TEXT_MUTED",
    "TEXT_PRIMARY",
    "YELLOW",
]
