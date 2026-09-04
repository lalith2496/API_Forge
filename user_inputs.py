"""
Helpers for USER_INPUT placeholders in generated test suites.
"""

import copy
import json
import re
from typing import Any, Dict, List, Optional

USER_INPUT_PREFIX = "USER_INPUT:"
USER_INPUT_PATTERN = re.compile(r"USER_INPUT[:_]([A-Za-z0-9_-]+)")


def field_to_env_key(field_name: str) -> str:
    """caseNumber -> USER_INPUT_CASE_NUMBER"""
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", field_name)
    snake = snake.replace("-", "_").upper()
    return f"USER_INPUT_{snake}"


def _placeholders_in_request(case: dict) -> set:
    """Unique field names referenced by USER_INPUT: in a case request."""
    blob = json.dumps(case.get("request", {}))
    return {m.group(1) for m in USER_INPUT_PATTERN.finditer(blob)}


def build_input_catalog(test_suite: dict) -> Dict[str, dict]:
    """
    One entry per field actually used in requests (deduplicated).

    Returns:
        {
          "caseNumber": {
            "hint": "Existing case in your tenant",
            "env_key": "USER_INPUT_CASE_NUMBER",
            "cases": ["TC-01"],
          },
        }
    """
    catalog: Dict[str, dict] = {}

    for case in test_suite.get("test_cases", []):
        case_id = case.get("id", "?")
        declared = case.get("user_inputs") or {}
        if not isinstance(declared, dict):
            declared = {}

        for name in sorted(_placeholders_in_request(case)):
            if name not in catalog:
                catalog[name] = {
                    "hint": "",
                    "env_key": field_to_env_key(name),
                    "cases": [],
                }
            if case_id not in catalog[name]["cases"]:
                catalog[name]["cases"].append(case_id)
            hint = declared.get(name)
            if isinstance(hint, str) and hint.strip() and not catalog[name]["hint"]:
                catalog[name]["hint"] = hint.strip()

    return catalog


def extract_user_input_fields(test_suite: dict) -> dict:
    """
    Scan for USER_INPUT placeholders in requests only.
    Returns {field_name: hint_or_empty_string}.
    """
    catalog = build_input_catalog(test_suite)
    return {name: meta["hint"] for name, meta in catalog.items()}


def cases_requiring_user_input(test_suite: dict) -> list:
    """Test case ids whose requests still contain USER_INPUT placeholders."""
    out = []
    for case in test_suite.get("test_cases", []):
        if _placeholders_in_request(case):
            out.append(case.get("id", "?"))
    return out


def summarize_test_cases(test_suite: dict, values: Optional[dict] = None) -> List[dict]:
    """Compact rows for UI tables."""
    suite = apply_user_inputs(test_suite, values or {})
    rows = []
    for case in suite.get("test_cases", []):
        ep = case.get("endpoint") or {}
        req = case.get("request") or {}
        method = ep.get("method") or req.get("method", "")
        path = ep.get("path") or req.get("path", "")
        rows.append({
            "id": case.get("id", "?"),
            "endpoint": f"{method} {path}".strip(),
            "category": case.get("category", ""),
            "description": case.get("description", ""),
            "expected": case.get("expected", {}).get("status_code"),
        })
    return rows


def _value_for(name: str, values: dict):
    if not values:
        return None
    env_key = field_to_env_key(name)
    return values.get(env_key) or values.get(name)


def replace_user_inputs(value: Any, values: dict):
    """Replace USER_INPUT:<field> placeholders with provided UI/env values."""
    if isinstance(value, str):
        def repl(m):
            val = _value_for(m.group(1), values)
            if val not in (None, ""):
                return str(val)
            return m.group(0)

        return USER_INPUT_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [replace_user_inputs(v, values) for v in value]
    if isinstance(value, dict):
        return {k: replace_user_inputs(v, values) for k, v in value.items()}
    return value


def apply_user_inputs(test_suite: dict, values: dict) -> dict:
    """Return a copy of the suite with USER_INPUT: placeholders replaced."""
    suite = copy.deepcopy(test_suite)
    for case in suite.get("test_cases", []):
        case["request"] = replace_user_inputs(case.get("request", {}), values)
        if case.get("requires_user_input") and not _request_has_placeholders(case):
            case["requires_user_input"] = False
        # Drop per-case metadata once values are applied (cleaner exports/display).
        if values and not _request_has_placeholders(case):
            case.pop("user_inputs", None)
    return suite


def _request_has_placeholders(case: dict) -> bool:
    return bool(_placeholders_in_request(case))


def build_user_input_env_lines(
    fields: Dict[str, str], values: Optional[Dict[str, str]] = None
) -> List[str]:
    """Lines for .env: USER_INPUT_CASE_NUMBER=<your value>"""
    lines = []
    values = values or {}
    for name in sorted(fields):
        key = field_to_env_key(name)
        val = _value_for(name, values) or ""
        hint = fields[name]
        comment = f"  # {hint}" if hint else ""
        lines.append(f"{key}={val}{comment}")
    return lines


def unresolved_fields(test_suite: dict, values: dict) -> list[str]:
    """Field names still using USER_INPUT placeholders in requests after applying values."""
    catalog = build_input_catalog(test_suite)
    missing = []
    for name in catalog:
        val = _value_for(name, values)
        if not str(val or "").strip():
            missing.append(name)
    return sorted(missing)


def _param_key(location: str, name: str) -> str:
    return f"{location}:{name}"


def _parse_param_key(key: str) -> tuple[str, str]:
    if ":" in key:
        loc, name = key.split(":", 1)
        return loc, name
    return "query", key


def build_request_params_catalog(test_suite: dict) -> Dict[str, dict]:
    """
    Collect editable query/path parameters used across test cases.

    Returns:
        {
          "query:status": {
            "location": "query",
            "name": "status",
            "sample": "active",
            "cases": ["TC-01"],
          },
        }
    """
    catalog: Dict[str, dict] = {}

    for case in test_suite.get("test_cases", []):
        if case.get("category") not in ("happy_path", "response_schema"):
            continue
        case_id = case.get("id", "?")
        req = case.get("request") or {}
        for location in ("query_params", "path_params"):
            params = req.get(location) or {}
            if not isinstance(params, dict):
                continue
            loc = "query" if location == "query_params" else "path"
            for name, raw in params.items():
                if not name:
                    continue
                key = _param_key(loc, str(name))
                sample = "" if raw is None else str(raw)
                if key not in catalog:
                    catalog[key] = {
                        "location": loc,
                        "name": str(name),
                        "sample": sample,
                        "cases": [],
                    }
                if case_id not in catalog[key]["cases"]:
                    catalog[key]["cases"].append(case_id)
                if not catalog[key]["sample"] and sample:
                    catalog[key]["sample"] = sample

    return catalog


def read_input_values_from_session(catalog: dict, session_state: Any, key_prefix: str) -> dict:
    """Read widget values from Streamlit session_state using stable widget keys."""
    return {
        name: str(session_state.get(f"{key_prefix}_{name}", "") or "").strip()
        for name in catalog
    }


def env_key_for_param(location: str, name: str) -> str:
    """query:limit -> REQUEST_QUERY_LIMIT"""
    prefix = "REQUEST_QUERY" if location == "query" else "REQUEST_PATH"
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    snake = snake.replace("-", "_").upper()
    return f"{prefix}_{snake}"


def read_param_values_from_session(catalog: dict, session_state: Any, key_prefix: str) -> dict:
    """Read request param widget values from Streamlit session_state."""
    out = {}
    for key in catalog:
        val = str(session_state.get(f"{key_prefix}_{key}", "") or "").strip()
        if val:
            out[key] = val
    return out


def apply_request_param_overrides(
    request: dict,
    overrides: Optional[dict],
    case_category: Optional[str] = None,
) -> dict:
    """
    Merge user-edited query/path params into a request dict.
    Only applies to happy_path/response_schema cases so negative tests keep bad values.
    Never injects params that are not already on the case request.
    """
    if not overrides:
        return request
    if case_category and case_category not in ("happy_path", "response_schema"):
        return copy.deepcopy(request or {})

    req = copy.deepcopy(request or {})
    query = dict(req.get("query_params") or {})
    path = dict(req.get("path_params") or {})
    for key, val in overrides.items():
        if val in (None, ""):
            continue
        loc, name = _parse_param_key(key)
        if loc == "path":
            if name not in path:
                continue
            path[name] = val
        else:
            if name not in query:
                continue
            query[name] = val
    req["query_params"] = query
    req["path_params"] = path
    return req

