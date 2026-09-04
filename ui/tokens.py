"""Shared neon Gen-Z design tokens for API Forge."""

from __future__ import annotations

# ── Neon accents ──────────────────────────────────────────────────────────
NEON_CYAN = "#00F5FF"
NEON_MAGENTA = "#FF00FF"
NEON_LIME = "#BFFF00"
NEON_PINK = "#FF006E"
NEON_YELLOW = "#FFE600"
NEON_PURPLE = "#BF5FFF"

# ── Backgrounds ───────────────────────────────────────────────────────────
BG_PAGE = "#0A0A0F"
BG_SURFACE = "#14101F"
BG_ELEVATED = "#1A1528"
BG_INPUT = "rgba(20,16,31,0.85)"
BG_CODE = "#120E1C"

# ── Text ────────────────────────────────────────────────────────────────────
TEXT_PRIMARY = "#F0F0FF"
TEXT_MUTED = "#8888AA"
TEXT_SUBTLE = "#5A5A78"

# ── Borders ─────────────────────────────────────────────────────────────────
BORDER_DEFAULT = "rgba(0,245,255,0.22)"
BORDER_STRONG = "rgba(0,245,255,0.45)"
BORDER_MUTED = "rgba(255,255,255,0.08)"

# ── Semantic ────────────────────────────────────────────────────────────────
COLOR_SUCCESS = NEON_LIME
COLOR_FAIL = NEON_PINK
COLOR_ERROR = NEON_YELLOW
COLOR_INFO = NEON_CYAN

# ── Result row palette (pandas styling) ─────────────────────────────────────
RESULT_PALETTE = {
    "✅ Pass": ("background-color:#0A2A0A", f"color:{NEON_LIME}"),
    "❌ Fail": ("background-color:#2A0014", f"color:{NEON_PINK}"),
    "⚠ Error": ("background-color:#2A2000", f"color:{NEON_YELLOW}"),
    "⏭ Skipped": ("background-color:#14101F", f"color:{TEXT_MUTED}"),
}

# ── ReDoc / iframe ──────────────────────────────────────────────────────────
REDOC_BG_MAIN = BG_PAGE
REDOC_BG_SECONDARY = BG_SURFACE
REDOC_BG_CODE = BG_CODE
REDOC_BG_ITEM = BG_ELEVATED
REDOC_BORDER = BORDER_MUTED
REDOC_TEXT_PRIMARY = TEXT_PRIMARY
REDOC_TEXT_MUTED = TEXT_MUTED
REDOC_ACCENT = NEON_CYAN

BADGE_GET = "#0099CC"
BADGE_POST = "#66FF00"
BADGE_PUT = "#FF9900"
BADGE_PATCH = "#BF5FFF"
BADGE_DELETE = NEON_PINK

REDOC_VERSION = "2.1.5"

FONT_HEADING = '"Space Grotesk", sans-serif'
FONT_BODY = '"Space Grotesk", sans-serif'
FONT_MONO = '"JetBrains Mono", monospace'


def font_import() -> str:
    return (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=JetBrains+Mono:wght@400;500;600&"
        "family=Space+Grotesk:wght@400;500;600;700&display=swap');"
    )


def generate_css_vars() -> str:
    return f"""
:root {{
  --neon-cyan: {NEON_CYAN};
  --neon-magenta: {NEON_MAGENTA};
  --neon-lime: {NEON_LIME};
  --neon-pink: {NEON_PINK};
  --neon-yellow: {NEON_YELLOW};
  --neon-purple: {NEON_PURPLE};
  --bg-page: {BG_PAGE};
  --bg-surface: {BG_SURFACE};
  --bg-elevated: {BG_ELEVATED};
  --bg-input: {BG_INPUT};
  --bg-code: {BG_CODE};
  --text-primary: {TEXT_PRIMARY};
  --text-muted: {TEXT_MUTED};
  --text-subtle: {TEXT_SUBTLE};
  --border-default: {BORDER_DEFAULT};
  --border-strong: {BORDER_STRONG};
  --border-muted: {BORDER_MUTED};
  --color-success: {COLOR_SUCCESS};
  --color-fail: {COLOR_FAIL};
  --color-error: {COLOR_ERROR};
  --color-info: {COLOR_INFO};
  --font-heading: {FONT_HEADING};
  --font-body: {FONT_BODY};
  --font-mono: {FONT_MONO};
}}
"""
