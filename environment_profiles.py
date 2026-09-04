"""UI-only DEV/QA/UAT/PROD environment profile helpers."""

from __future__ import annotations

from typing import Any

TIERS = ("DEV", "QA", "UAT", "PROD")

_DEFAULT_PROFILE = {
    "API_BASE_URL": "",
    "ACCESS_TOKEN": "",
    "API_KEY": "",
    "_AUTH_TYPE": "Bearer",
    "_CUSTOM_HEADER_NAME": "X-Api-Key",
}


def default_profiles() -> dict[str, dict[str, str]]:
    return {tier: dict(_DEFAULT_PROFILE) for tier in TIERS}


def profile_env_key(selection_key: str, tier: str) -> str:
    return f"{selection_key}:{tier}"


def get_profile(profiles: dict, tier: str) -> dict[str, str]:
    base = dict(_DEFAULT_PROFILE)
    base.update(profiles.get(tier) or {})
    return base


def save_profile(profiles: dict, tier: str, values: dict[str, Any]) -> dict:
    out = dict(profiles or default_profiles())
    if tier not in out:
        out[tier] = dict(_DEFAULT_PROFILE)
    for key, val in (values or {}).items():
        if key.startswith("_") or key.isupper() or key == "API_BASE_URL":
            out[tier][key] = str(val or "")
    return out


def prod_guardrails(tier: str) -> dict:
    """Suggested run defaults per tier."""
    if tier == "PROD":
        return {
            "max_concurrency": 2,
            "skip_rate_limit_default": True,
            "require_confirmation": True,
            "security_scan_default": True,
        }
    return {
        "max_concurrency": 5,
        "skip_rate_limit_default": True,
        "require_confirmation": False,
        "security_scan_default": True,
    }


def export_profile_text(tier: str, profile: dict) -> str:
    lines = [f"# API Forge profile — {tier}", ""]
    for key in sorted(profile.keys()):
        if key.startswith("_"):
            continue
        lines.append(f"{key}={profile.get(key, '')}")
    return "\n".join(lines) + "\n"
