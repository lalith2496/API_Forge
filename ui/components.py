"""Reusable UI components and theme injection for API Forge."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from ui import tokens

_STYLES_PATH = Path(__file__).parent / "styles.css"


def inject_theme() -> None:
    """Inject neon Gen-Z CSS and design tokens into the Streamlit page."""
    css = _STYLES_PATH.read_text(encoding="utf-8")
    st.markdown(
        f"<style>{tokens.font_import()}{tokens.generate_css_vars()}{css}</style>",
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    """Render the marketing hero banner."""
    st.markdown(
        """
<div class="forge-hero">
  <h1>API Forge</h1>
  <p class="forge-hero-sub">Generate, run, and export API test suites from OpenAPI specs, Postman collections, or cURL commands.</p>
  <div class="forge-chips">
    <span class="forge-chip">OpenAPI 3 · Swagger 2</span>
    <span class="forge-chip">Postman · cURL</span>
    <span class="forge-chip">Postman · Pytest</span>
    <span class="forge-chip">In-browser runner</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def step(n: int, label: str) -> None:
    """Render a styled numbered step heading."""
    st.markdown(
        f'<div class="step-hdr">'
        f'<span class="step-num">{n}</span>'
        f'<span class="step-lbl">{label}</span>'
        f'<div class="step-rule"></div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def sec(label: str) -> None:
    """Render a small-caps section label."""
    st.markdown(f'<p class="sec-label">{label}</p>', unsafe_allow_html=True)


def colour_results(df: pd.DataFrame):
    """Apply neon semantic row colors to a results dataframe."""
    palette = tokens.RESULT_PALETTE

    def _row(row):
        bg, fg = palette.get(row["Result"], ("", ""))
        return [f"{bg};{fg}"] * len(row)

    return df.style.apply(_row, axis=1)


def render_auth_panel(selection_key: str, runner_env: dict) -> dict:
    """
    Always-visible authentication panel. Updates runner_env in session.
    Returns updated runner_env dict.
    """
    sec("Authentication")
    st.caption(
        "Paste your access token and/or API key to run tests in the browser. "
        "Values stay in this session only — not saved unless you download `.env`."
    )

    c1, c2 = st.columns(2)
    with c1:
        token_val = st.text_input(
            "Access token",
            value=str(runner_env.get("ACCESS_TOKEN", "") or ""),
            type="password",
            key=f"runner_auth_token_{selection_key}",
            help="Maps to VALID_TOKEN in generated requests.",
        )
        runner_env["ACCESS_TOKEN"] = token_val
    with c2:
        api_key = st.text_input(
            "API key",
            value=str(runner_env.get("API_KEY", "") or ""),
            type="password",
            key=f"runner_auth_apikey_{selection_key}",
            help="Injected as the Key header when missing from the request.",
        )
        runner_env["API_KEY"] = api_key

    if token_val.strip() or api_key.strip():
        st.success("Auth credentials set — injected for non-auth tests missing headers.")

    return runner_env

