"""Invalid / broken ID test case helpers for query and path parameters."""

from __future__ import annotations

import copy
import re
from typing import Optional

import ingester

_ID_PATTERN = re.compile(
    r"(^id$|_id$|_ids$|^ids$|id$|ids$|uuid|guid|contentid|articleid|resourceid|objectid|entityid)",
    re.IGNORECASE,
)

BROKEN_ID_VALUES = (
    "00000000-0000-0000-0000-000000000000",
    "999999999999",
    "not-a-valid-id",
    "invalid-id-format-xyz",
    "nonexistent-article-id-000000",
)


def is_id_like_param(name: str, schema: Optional[dict] = None) -> bool:
    """True when a parameter name or schema suggests an identifier."""
    if not name:
        return False
    normalized = name.replace("_", "").replace("-", "")
    if _ID_PATTERN.search(normalized) or _ID_PATTERN.search(name):
        return True
    if schema and schema.get("format") in ("uuid", "guid"):
        return True
    lower = name.lower()
    return lower.endswith("id") or lower.endswith("ids") or "contentid" in lower


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _pick_error_status(norm: dict, preferred: tuple[str, ...] = ("400", "404", "422", "403")) -> int:
    responses = norm.get("responses") or {}
    for code in preferred:
        if code in responses:
            return int(code)
    return int(preferred[0])


def _suite_has_invalid_id_case(suite: dict, ep_t: tuple[str, str], param_name: str) -> bool:
    needle = param_name.lower()
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        if _endpoint_tuple(ep) != ep_t:
            continue
        blob = " ".join([
            case.get("description") or "",
            case.get("notes") or "",
            str((case.get("request") or {}).get("query_params") or {}),
            str((case.get("request") or {}).get("path_params") or {}),
        ]).lower()
        if needle not in blob:
            continue
        if any(x in blob for x in ("invalid", "non-existent", "nonexistent", "broken", "not-a-valid", "00000000")):
            return True
        if "vector:broken_id" in (case.get("notes") or "").lower():
            return True
    return False


def _set_param(request: dict, location: str, name: str, value: str) -> None:
    if location == "path":
        request["path_params"] = dict(request.get("path_params") or {})
        request["path_params"][name] = value
    else:
        request["query_params"] = dict(request.get("query_params") or {})
        request["query_params"][name] = value


def _make_case(endpoint, category, description, request, status, notes, case_id):
    return {
        "id": case_id,
        "endpoint": {"method": endpoint["method"], "path": endpoint["path"]},
        "category": category,
        "description": description,
        "requires_user_input": False,
        "request": request,
        "expected": {"status_code": status, "response_assertions": []},
        "notes": notes,
    }


def supplement_invalid_id_cases(
    test_suite: dict,
    norm_map: Optional[dict],
    base_request_fn,
) -> dict:
    """
    Always add invalid/non-existent ID retrieval cases when missing.
    base_request_fn(endpoint, norm) -> request dict
    """
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    new_cases = []
    idx = 1

    for ep in suite.get("endpoints") or []:
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue
        ep_t = _endpoint_tuple(ep)
        base = base_request_fn(ep, norm)
        status = _pick_error_status(norm, ("400", "404", "422"))

        for param in norm.get("parameters") or []:
            name = param.get("name")
            loc = param.get("in") or "query"
            if loc not in ("query", "path") or not name:
                continue
            schema = param.get("schema") or {}
            if not is_id_like_param(name, schema):
                continue
            if _suite_has_invalid_id_case(suite, ep_t, name):
                continue

            bad_value = BROKEN_ID_VALUES[0]
            if "ids" in name.lower():
                bad_value = f"{BROKEN_ID_VALUES[0]},{BROKEN_ID_VALUES[2]}"

            req_validation = copy.deepcopy(base)
            _set_param(req_validation, loc, name, bad_value)
            new_cases.append(_make_case(
                ep,
                "validation",
                f"Retrieve with invalid/non-existent '{name}' value",
                req_validation,
                status,
                "Auto-generated invalid ID retrieval case",
                f"TC-ID-{idx:02d}",
            ))
            idx += 1

            req_security = copy.deepcopy(base)
            _set_param(req_security, loc, name, BROKEN_ID_VALUES[2])
            new_cases.append(_make_case(
                ep,
                "security",
                f"Broken object ID in '{name}' (non-existent resource)",
                req_security,
                status,
                "Auto-generated security case vector:broken_id",
                f"TC-ID-{idx:02d}",
            ))
            idx += 1

    if not new_cases:
        return suite

    suite["test_cases"] = (suite.get("test_cases") or []) + new_cases
    for i, case in enumerate(suite["test_cases"], start=1):
        case["id"] = f"TC-{i:02d}"
    return suite
