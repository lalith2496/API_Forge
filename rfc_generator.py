"""RFC-aware test case generation (9110 semantics, 7807, 6265)."""

from __future__ import annotations

import copy
from typing import Optional

import ingester
import negative_generator

_RFC_CATEGORIES = frozenset({"rfc_semantics", "rfc_problem", "rfc_cookies"})


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _existing_rfc_keys(suite: dict) -> set[tuple]:
    keys = set()
    for case in suite.get("test_cases") or []:
        if case.get("category") in _RFC_CATEGORIES:
            ep = case.get("endpoint") or {}
            keys.add((*_endpoint_tuple(ep), case.get("category", ""), (case.get("description") or "")[:35].lower()))
    return keys


def _make_rfc_case(endpoint, category, description, request, status, case_id, assertions=None):
    return {
        "id": case_id,
        "endpoint": {"method": endpoint["method"], "path": endpoint["path"]},
        "category": category,
        "description": description,
        "requires_user_input": False,
        "request": request,
        "expected": {
            "status_code": status,
            "response_assertions": assertions or [],
        },
        "notes": "Auto-generated RFC-aware case",
    }


def _rfc_cases_for_endpoint(endpoint, norm, start_idx, existing):
    out = []
    ep_t = _endpoint_tuple(endpoint)
    base = negative_generator._base_request(endpoint, norm)
    method = endpoint["method"]

    def _add(category, description, request, status, assertions=None):
        key = (*ep_t, category, description[:35].lower())
        if key in existing:
            return
        existing.add(key)
        out.append(_make_rfc_case(
            endpoint, category, description, request, status,
            f"TC-RFC-{start_idx + len(out):02d}", assertions,
        ))

    wrong_method = copy.deepcopy(base)
    alt = "POST" if method == "GET" else "GET"
    wrong_method["method"] = alt
    _add(
        "rfc_semantics",
        f"Wrong HTTP method (RFC 9110 — expect 405)",
        wrong_method,
        negative_generator._pick_error_status(norm, ("405", "404", "400")),
    )

    bad_accept = copy.deepcopy(base)
    bad_accept["headers"] = dict(bad_accept.get("headers") or {})
    bad_accept["headers"]["Accept"] = "application/xml, application/unknown"
    _add(
        "rfc_semantics",
        "Unacceptable Accept header (RFC 9110 — expect 406)",
        bad_accept,
        negative_generator._pick_error_status(norm, ("406", "400", "404")),
    )

    if method in ("POST", "PUT", "PATCH") and base.get("body") is not None:
        bad_ct = copy.deepcopy(base)
        bad_ct["headers"] = dict(bad_ct.get("headers") or {})
        bad_ct["headers"]["Content-Type"] = "text/plain"
        _add(
            "rfc_semantics",
            "Unsupported Content-Type (RFC 9110 — expect 415)",
            bad_ct,
            negative_generator._pick_error_status(norm, ("415", "400", "422")),
        )

        bad_body = copy.deepcopy(base)
        bad_body["body"] = {"__invalid__": True}
        _add(
            "rfc_problem",
            "Malformed body expecting RFC 7807 problem response",
            bad_body,
            negative_generator._pick_error_status(norm, ("400", "422", "415")),
            [{"type": "problem_json"}],
        )

    return out


def supplement_rfc_cases(test_suite: dict, norm_map: Optional[dict], min_per_endpoint: int = 1) -> dict:
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    existing = _existing_rfc_keys(suite)

    counts = {}
    for case in suite.get("test_cases") or []:
        if case.get("category") in _RFC_CATEGORIES:
            t = _endpoint_tuple(case.get("endpoint") or {})
            counts[t] = counts.get(t, 0) + 1

    auto = []
    idx = 1
    for ep in suite.get("endpoints") or []:
        ep_t = _endpoint_tuple(ep)
        if counts.get(ep_t, 0) >= min_per_endpoint:
            continue
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue
        generated = _rfc_cases_for_endpoint(ep, norm, idx, existing)
        auto.extend(generated)
        idx += len(generated)

    if not auto:
        return suite

    suite["test_cases"] = (suite.get("test_cases") or []) + auto
    for i, case in enumerate(suite["test_cases"], start=1):
        case["id"] = f"TC-{i:02d}"
    return suite
