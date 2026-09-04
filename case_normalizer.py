"""Reclassify LLM-generated cases that deviate from the OpenAPI spec."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Optional

import canonical_templates
import ingester
import parameter_discovery

_HAPPY_CATEGORIES = frozenset({"happy_path", "response_schema"})
_RECLASSIFY_CATEGORIES = frozenset({"happy_path", "response_schema", "optional_fields"})

_NEGATIVE_DESC = re.compile(
    r"\b(null|invalid|missing|unsupported|extra|wrong|without|empty|bad|malformed|"
    r"no\s+\w+|incorrect|unexpected|unknown)\b",
    re.IGNORECASE,
)
_AUTH_NEGATIVE_DESC = re.compile(
    r"\b(missing|invalid|expired|empty|no)\b.*\b(auth|authorization|bearer|token|api\s*key|key\s*header)\b"
    r"|\b(auth|authorization|bearer|token|api\s*key)\b.*\b(missing|invalid|expired|without|empty)\b",
    re.IGNORECASE,
)


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _spec_query_names(norm: dict) -> set[str]:
    return {
        p["name"]
        for p in parameter_discovery.spec_parameters(norm)
        if p.get("name") and (p.get("in") or "query") == "query"
    }


def _spec_path_names(norm: dict) -> set[str]:
    return {
        p["name"]
        for p in parameter_discovery.spec_parameters(norm)
        if p.get("name") and p.get("in") == "path"
    }


def _reference_request(norm: dict) -> dict:
    return canonical_templates.build_reference_request(
        {**norm, "parameters": parameter_discovery.spec_parameters(norm)}
    )


def _json_equal(a: Any, b: Any) -> bool:
    try:
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    except TypeError:
        return a == b


def _request_deviates(req: dict, ref_req: dict, norm: dict) -> list[str]:
    issues: list[str] = []
    spec_qp = _spec_query_names(norm)
    actual_qp = set((req.get("query_params") or {}).keys())
    extra_qp = actual_qp - spec_qp
    if extra_qp:
        issues.append("extra_query")

    spec_pp = _spec_path_names(norm)
    actual_pp = set((req.get("path_params") or {}).keys())
    if actual_pp - spec_pp:
        issues.append("extra_path")

    ref_body, _, _, body_required = canonical_templates.build_reference_body(norm)
    body = req.get("body")
    if body_required and body in (None, {}, []):
        issues.append("missing_body")
    elif ref_body is not None and body is not None and not _json_equal(body, ref_body):
        issues.append("body_mismatch")
    elif ref_body is not None and body is None and body_required:
        issues.append("missing_body")

    return issues


def _mark_validation_400(case: dict, reason: str) -> None:
    case["category"] = "validation"
    expected = case.setdefault("expected", {})
    expected["status_code"] = 400
    notes = case.get("notes") or ""
    token = f"spec_deviation:{reason}"
    if token not in notes:
        case["notes"] = f"{notes} {token}".strip()


def _mark_auth_case(case: dict, norm: dict) -> None:
    case["category"] = "auth"
    expected = case.setdefault("expected", {})
    responses = norm.get("responses") or {}
    for code in ("401", "403", "400"):
        if code in responses:
            expected["status_code"] = int(code)
            break
    else:
        expected["status_code"] = 401


def normalize_generated_cases(test_suite: dict, norm_map: Optional[dict]) -> dict:
    """
    Fix mislabeled LLM cases:
    - Only one true happy_path per endpoint
    - Extra query/path params or bad body → validation 400
    - Auth-negative tests labeled happy_path → auth
    - optional_fields → validation 400
    """
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    happy_seen: dict[tuple[str, str], str] = {}

    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue

        category = case.get("category") or ""
        desc = case.get("description") or ""
        req = case.get("request") or {}
        ref_req = _reference_request(norm)
        ep_t = _endpoint_tuple(ep)
        issues = _request_deviates(req, ref_req, norm)

        if category == "optional_fields":
            _mark_validation_400(case, "optional_fields")
            continue

        if category not in _HAPPY_CATEGORIES:
            if issues and category not in ("auth", "security", "rfc_semantics", "rfc_problem"):
                _mark_validation_400(case, issues[0])
            continue

        if _AUTH_NEGATIVE_DESC.search(desc):
            _mark_auth_case(case, norm)
            continue

        if issues or _NEGATIVE_DESC.search(desc):
            _mark_validation_400(case, issues[0] if issues else "description")
            continue

        if category == "happy_path":
            if ep_t in happy_seen:
                if _AUTH_NEGATIVE_DESC.search(desc):
                    _mark_auth_case(case, norm)
                else:
                    _mark_validation_400(case, "duplicate_happy_path")
                continue
            happy_seen[ep_t] = case.get("id", "")

    return suite
