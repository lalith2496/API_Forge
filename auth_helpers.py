"""Auth header injection for in-browser test runner."""

from __future__ import annotations

import copy
import re
from typing import Any, Optional

AUTH_TYPES = ("None", "Bearer", "API Key header")

# Categories where the LLM intentionally tests missing/invalid auth — do not inject.
_AUTH_TEST_CATEGORIES = frozenset({"auth"})
_HAPPY_CATEGORIES = frozenset({"happy_path", "response_schema"})

_API_KEY_HEADER_NAMES = frozenset({"key", "x-api-key", "api-key", "apikey"})

_AUTH_NEGATIVE_DESC = re.compile(
    r"\b(missing|invalid|expired|empty|no)\b.*\b(auth|authorization|bearer|token|api\s*key|key\s*header)\b"
    r"|\b(auth|authorization|bearer|token|api\s*key)\b.*\b(missing|invalid|expired|without|empty)\b",
    re.IGNORECASE,
)


def strip_bearer_prefix(value: str) -> str:
    """Remove one or more leading Bearer prefixes (handles pasted tokens)."""
    value = str(value or "").strip()
    while value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def _header_present(headers: dict, name: str) -> bool:
    target = name.lower()
    return any(k.lower() == target for k in (headers or {}))


def _is_intentionally_empty_auth_value(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in ("", "bearer")


def _request_auth_header_value(case: Optional[dict], header_name: str) -> Any:
    if not case:
        return None
    target = header_name.lower()
    for key, value in ((case.get("request") or {}).get("headers") or {}).items():
        if str(key).lower() == target:
            return value
    return None


def is_auth_negative_case(case: Optional[dict]) -> bool:
    """True when the test intentionally omits, empties, or invalidates auth."""
    if not case:
        return False
    if case.get("category") in _AUTH_TEST_CATEGORIES:
        return True
    if _is_auth_negative_security(case):
        return True
    desc = case.get("description") or ""
    if _AUTH_NEGATIVE_DESC.search(desc):
        return True
    auth_val = _request_auth_header_value(case, "Authorization")
    if auth_val is not None and _is_intentionally_empty_auth_value(auth_val):
        return True
    for key in _API_KEY_HEADER_NAMES:
        key_val = _request_auth_header_value(case, key)
        if key_val is not None and _is_intentionally_empty_auth_value(key_val):
            return True
    return False


def _is_auth_negative_security(case: dict) -> bool:
    if case.get("category") != "security":
        return False
    notes = (case.get("notes") or "").lower()
    desc = (case.get("description") or "").lower()
    return (
        "vector:auth" in notes
        or "authorization" in desc
        or "token" in desc
        or "api key" in desc
    )


def auth_header_names_from_security(norm_endpoint: Optional[dict]) -> set[str]:
    """Lowercase header names declared by OpenAPI security schemes."""
    names: set[str] = set()
    for sec in (norm_endpoint or {}).get("security") or []:
        if not isinstance(sec, dict):
            continue
        scheme_type = (sec.get("type") or "").lower()
        if scheme_type in {"http", "oauth2"}:
            scheme = (sec.get("scheme") or "bearer").lower()
            if scheme_type == "oauth2" or scheme == "bearer":
                names.add("authorization")
        elif scheme_type == "apikey" and (sec.get("in") or "header").lower() == "header":
            param = sec.get("parameterName") or sec.get("name") or "X-Api-Key"
            names.add(str(param).lower())
    return names


def build_reference_auth_headers(norm_endpoint: Optional[dict]) -> dict[str, str]:
    """
    Canonical auth headers from OpenAPI security:
    - Bearer / OAuth2 → Authorization: Bearer VALID_TOKEN
    - API key in header → <name>: API_KEY
    """
    headers: dict[str, str] = {}
    if not norm_endpoint:
        return headers

    for sec in norm_endpoint.get("security") or []:
        if not isinstance(sec, dict):
            continue
        scheme_type = (sec.get("type") or "").lower()

        if scheme_type == "http":
            scheme = (sec.get("scheme") or "").lower()
            if scheme == "bearer":
                headers["Authorization"] = "Bearer VALID_TOKEN"
        elif scheme_type == "oauth2":
            headers["Authorization"] = "Bearer VALID_TOKEN"
        elif scheme_type == "apikey" and (sec.get("in") or "header").lower() == "header":
            param = sec.get("parameterName") or sec.get("name") or "X-Api-Key"
            headers[str(param)] = "API_KEY"

    return headers


def resolve_header_value(
    header_name: str,
    value: Any,
    env_vals: Optional[dict] = None,
    case: Optional[dict] = None,
) -> Any:
    """Replace auth placeholders with the correct session credential per header."""
    env_vals = env_vals or {}
    if not isinstance(value, str):
        return value

    s = value
    lname = header_name.lower()
    access_token = strip_bearer_prefix(env_vals.get("ACCESS_TOKEN", "") or "")
    api_key = str(env_vals.get("API_KEY", "") or "").strip()
    auth_negative = is_auth_negative_case(case)

    if lname == "authorization":
        if "INVALID_TOKEN" in s:
            s = s.replace(
                "INVALID_TOKEN",
                str(env_vals.get("INVALID_TOKEN", "invalid_token_for_testing")),
            )
        if "EXPIRED_TOKEN" in s:
            s = s.replace(
                "EXPIRED_TOKEN",
                str(env_vals.get("EXPIRED_TOKEN", "expired_token_for_testing")),
            )
        if auth_negative:
            return s
        if "VALID_TOKEN" in s:
            s = s.replace("VALID_TOKEN", access_token)
        if "API_KEY" in s:
            s = s.replace("API_KEY", access_token)
        if not access_token:
            return s
        if s.strip().lower() in ("bearer", ""):
            return f"Bearer {access_token}"
        if s.lower().startswith("bearer "):
            return f"Bearer {strip_bearer_prefix(s)}"
        return s

    if lname in _API_KEY_HEADER_NAMES:
        if auth_negative:
            return s
        if "API_KEY" in s:
            s = s.replace("API_KEY", api_key)
        if "VALID_TOKEN" in s:
            s = s.replace("VALID_TOKEN", api_key)
        if s.lower().startswith("bearer "):
            return strip_bearer_prefix(s)
        return s

    if "API_KEY" in s:
        s = s.replace("API_KEY", api_key)
    if "VALID_TOKEN" in s:
        s = s.replace("VALID_TOKEN", access_token)
    return s


def should_inject_auth(case: dict, headers: dict) -> bool:
    """True when we may add auth headers without breaking negative auth tests."""
    if is_auth_negative_case(case):
        return False
    return True


def apply_auth_headers(
    headers: dict,
    case: dict,
    env_vals: Optional[dict] = None,
) -> dict:
    """
    Inject session Bearer token and/or API key when missing from the request.
    Skips auth-category and intentional auth-negative security tests.
    """
    env_vals = env_vals or {}
    out = dict(headers or {})

    if not should_inject_auth(case, out):
        return out

    token = strip_bearer_prefix(env_vals.get("ACCESS_TOKEN", "") or "")
    api_key = str(env_vals.get("API_KEY", "") or "").strip()

    if token and not _header_present(out, "Authorization"):
        out["Authorization"] = f"Bearer {token}"

    if api_key and not _header_present(out, "Key") and not _header_present(out, "X-Api-Key"):
        out["Key"] = api_key

    return out


def inject_spec_auth_headers(test_suite: dict, norm_map: Optional[dict]) -> dict:
    """
    Happy-path cases use spec-correct auth headers:
    Bearer token in Authorization, API key in the Key (or named) header — not the same value.
    """
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    import ingester

    suite = copy.deepcopy(test_suite)
    for case in suite.get("test_cases") or []:
        if case.get("category") not in _HAPPY_CATEGORIES:
            continue

        norm = ingester.lookup_norm(norm_map, case.get("endpoint") or {})
        if not norm:
            continue

        ref_auth = build_reference_auth_headers(norm)
        if not ref_auth:
            continue

        auth_names = auth_header_names_from_security(norm)
        req = case.setdefault("request", {})
        headers = dict(req.get("headers") or {})
        headers = {
            k: v for k, v in headers.items()
            if k.lower() not in auth_names
        }
        headers.update(ref_auth)
        req["headers"] = headers

    return suite
