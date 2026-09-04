"""Rule-based security negative test case generation."""

from __future__ import annotations

import copy
from typing import Optional

import canonical_templates
import ingester
import id_cases
import negative_generator

_SECURITY_VECTORS = {
    "sqli": ["' OR 1=1--", "'; DROP TABLE users--", "1; SELECT * FROM users"],
    "xss": ["<script>alert(1)</script>", '"><img src=x onerror=alert(1)>', "javascript:alert(1)"],
    "oversized": None,
    "invalid_date": ["not-a-date", "2024-13-40", "99/99/9999"],
    "broken_id": ["00000000-0000-0000-0000-000000000000", "999999999", "not-a-valid-id", "../../../../etc/passwd"],
}

_SECURITY_CATEGORIES = frozenset({"security"})


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _existing_security_keys(suite: dict) -> set[tuple]:
    keys = set()
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        notes = case.get("notes") or ""
        vector = ""
        if "vector:" in notes:
            vector = notes.split("vector:")[-1].strip().split()[0]
        if case.get("category") in _SECURITY_CATEGORIES:
            keys.add((*_endpoint_tuple(ep), vector or (case.get("description") or "")[:30].lower()))
    return keys


def _make_security_case(
    endpoint: dict,
    description: str,
    request: dict,
    status_code: int,
    vector: str,
    case_id: str,
) -> dict:
    return {
        "id": case_id,
        "endpoint": {"method": endpoint["method"], "path": endpoint["path"]},
        "category": "security",
        "description": description,
        "requires_user_input": False,
        "request": request,
        "expected": {"status_code": status_code, "response_assertions": []},
        "notes": f"Auto-generated security case vector:{vector}",
    }


def _security_cases_for_endpoint(
    endpoint: dict,
    norm: dict,
    start_idx: int,
    existing: set[tuple],
) -> list[dict]:
    out = []
    ep_t = _endpoint_tuple(endpoint)
    base = negative_generator._base_request(endpoint, norm)
    body, _, field_meta, _ = canonical_templates.build_canonical_body(norm)
    status = negative_generator._pick_error_status(norm, ("400", "422", "403", "404"))

    def _add(vector: str, description: str, request: dict, code: int = status) -> None:
        key = (*ep_t, vector, description[:50].lower())
        if key in existing:
            return
        existing.add(key)
        out.append(_make_security_case(
            endpoint, description, request, code, vector, f"TC-SEC-{start_idx + len(out):02d}"
        ))

    for param in norm.get("parameters") or []:
        pname = param.get("name")
        loc = param.get("in") or "query"
        if not pname or loc not in ("query", "path"):
            continue
        schema = param.get("schema") or {}
        if not id_cases.is_id_like_param(pname, schema):
            continue
        for bad_id in _SECURITY_VECTORS["broken_id"][:3]:
            req = copy.deepcopy(base)
            if loc == "path":
                req["path_params"] = dict(req.get("path_params") or {})
                req["path_params"][pname] = bad_id
            else:
                req["query_params"] = dict(req.get("query_params") or {})
                val = bad_id
                if "ids" in pname.lower():
                    val = f"{bad_id},{_SECURITY_VECTORS['broken_id'][1]}"
                req["query_params"][pname] = val
            _add(
                "broken_id",
                f"Broken/non-existent ID in '{pname}'",
                req,
                negative_generator._pick_error_status(norm, ("404", "400", "422")),
            )

    for field in field_meta:
        fpath = field.get("path", field.get("name", ""))
        ftype = field.get("type", "string")
        fmt = field.get("format")

        if field.get("enum"):
            bad = copy.deepcopy(base)
            if isinstance(bad.get("body"), dict):
                bad["body"] = canonical_templates.mutate_field_value(
                    bad["body"], fpath, "___INVALID_ENUM___"
                )
            _add("invalid_enum", f"Invalid enum for '{fpath}'", bad)

        if ftype == "string" or ftype is None:
            for payload in _SECURITY_VECTORS["sqli"][:2]:
                req = copy.deepcopy(base)
                if isinstance(req.get("body"), dict):
                    req["body"] = canonical_templates.mutate_field_value(req["body"], fpath, payload)
                elif fpath in (req.get("query_params") or {}):
                    req["query_params"] = dict(req["query_params"])
                    req["query_params"][fpath] = payload
                _add("sqli", f"SQL injection in '{fpath}'", req)

            for payload in _SECURITY_VECTORS["xss"][:2]:
                req = copy.deepcopy(base)
                if isinstance(req.get("body"), dict):
                    req["body"] = canonical_templates.mutate_field_value(req["body"], fpath, payload)
                _add("xss", f"XSS payload in '{fpath}'", req)

            max_len = field.get("maxLength")
            size = (max_len + 1) if max_len else 4096
            req = copy.deepcopy(base)
            if isinstance(req.get("body"), dict):
                req["body"] = canonical_templates.mutate_field_value(req["body"], fpath, "x" * min(size, 8192))
            _add("oversized", f"Oversized string in '{fpath}'", req)

        if fmt in ("date", "date-time") or "date" in str(fpath).lower():
            for bad_date in _SECURITY_VECTORS["invalid_date"][:2]:
                req = copy.deepcopy(base)
                if isinstance(req.get("body"), dict):
                    req["body"] = canonical_templates.mutate_field_value(req["body"], fpath, bad_date)
                _add("invalid_date", f"Invalid date in '{fpath}'", req)

        if fmt == "uuid" or id_cases.is_id_like_param(fpath, {"format": fmt} if fmt else None):
            for bad_id in _SECURITY_VECTORS["broken_id"][:2]:
                req = copy.deepcopy(base)
                if isinstance(req.get("body"), dict):
                    req["body"] = canonical_templates.mutate_field_value(req["body"], fpath, bad_id)
                elif fpath in (req.get("path_params") or {}):
                    req["path_params"] = dict(req["path_params"])
                    req["path_params"][fpath] = bad_id
                elif fpath in (req.get("query_params") or {}):
                    req["query_params"] = dict(req["query_params"])
                    req["query_params"][fpath] = bad_id
                _add("broken_id", f"Broken ID in '{fpath}'", req)

    if norm.get("security"):
        expired = copy.deepcopy(base)
        expired["headers"] = dict(expired.get("headers") or {})
        expired["headers"]["Authorization"] = "Bearer EXPIRED_TOKEN"
        _add(
            "auth_expired",
            "Expired bearer token",
            expired,
            negative_generator._pick_error_status(norm, ("401", "403")),
        )

        for sec in norm.get("security") or []:
            sec_type = (sec.get("type") or "").lower()
            if sec_type == "apikey":
                param = sec.get("parameterName") or sec.get("name") or "X-Api-Key"
                wrong = copy.deepcopy(base)
                wrong["headers"] = dict(wrong.get("headers") or {})
                wrong["headers"][str(param)] = "INVALID_TOKEN"
                _add("auth_apikey", f"Invalid API key header {param}", wrong, 401)

    return out


def supplement_security_cases(
    test_suite: dict,
    norm_map: Optional[dict],
    min_security_per_endpoint: int = 2,
) -> dict:
    """Add security test cases when LLM under-generated them."""
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    existing = _existing_security_keys(suite)

    counts: dict[tuple[str, str], int] = {}
    for case in suite.get("test_cases") or []:
        if case.get("category") in _SECURITY_CATEGORIES:
            t = _endpoint_tuple(case.get("endpoint") or {})
            counts[t] = counts.get(t, 0) + 1

    auto_cases = []
    auto_idx = 1
    for ep in suite.get("endpoints") or []:
        ep_t = _endpoint_tuple(ep)
        if counts.get(ep_t, 0) >= min_security_per_endpoint:
            continue
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue
        generated = _security_cases_for_endpoint(ep, norm, auto_idx, existing)
        auto_cases.extend(generated)
        auto_idx += len(generated)

    if not auto_cases:
        return suite

    suite["test_cases"] = (suite.get("test_cases") or []) + auto_cases
    for idx, case in enumerate(suite["test_cases"], start=1):
        case["id"] = f"TC-{idx:02d}"
    return suite
