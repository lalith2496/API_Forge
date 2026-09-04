"""Build and inject request bodies from OpenAPI / imported endpoint metadata."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Optional

import canonical_templates
import parameter_discovery

BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_HAPPY_CATEGORIES = frozenset({"happy_path", "response_schema"})
_NEGATIVE_BODY_CATEGORIES = frozenset({
    "validation", "boundary", "security", "rfc_semantics", "rfc_problem", "rfc_cookies",
})
_SKIP_PAYLOAD_ENFORCE = frozenset({
    "happy_path", "response_schema", "auth", "rfc_semantics",
})

_EMPTY_BODY_DESC = re.compile(
    r"\b(empty|null|missing|no)\b.*\b(body|payload|request body)\b"
    r"|\b(body|payload)\b.*\b(empty|null|missing|without)\b",
    re.IGNORECASE,
)


def example_from_schema(schema: dict, depth: int = 0) -> Any:
    """Build example from schema (all properties for objects)."""
    return canonical_templates._full_example_from_schema(schema, depth)


def extract_spec_body(norm_endpoint: Optional[dict]) -> tuple[Any, str, bool]:
    """Return (body, content_type, body_required) using exact reference payload."""
    body, content_type, _, body_required = canonical_templates.build_reference_body(norm_endpoint)
    return body, content_type, body_required


def is_intentionally_empty_body_case(case: dict) -> bool:
    """True when the test deliberately sends no / empty request body."""
    desc = case.get("description") or ""
    notes = (case.get("notes") or "").lower()
    if _EMPTY_BODY_DESC.search(desc):
        return True
    if "empty_body" in notes or "missing_body" in notes:
        return True
    body = (case.get("request") or {}).get("body")
    if body in (None, {}, []) and _EMPTY_BODY_DESC.search(desc):
        return True
    return False


def _should_inject_body(case: dict, has_body: bool) -> bool:
    if not has_body:
        return False
    if is_intentionally_empty_body_case(case):
        return False
    category = case.get("category") or ""
    if category in _NEGATIVE_BODY_CATEGORIES:
        return False
    return True


def _apply_reference_request(req: dict, ref_req: dict, content_type: str) -> None:
    req["query_params"] = copy.deepcopy(ref_req.get("query_params") or {})
    req["path_params"] = copy.deepcopy(ref_req.get("path_params") or {})
    if ref_req.get("body") is not None:
        req["body"] = copy.deepcopy(ref_req["body"])
    headers = req.setdefault("headers", {})
    if content_type and not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = content_type


def inject_spec_bodies(test_suite: dict, norm_map: Optional[dict]) -> dict:
    """
    Ensure happy-path cases use the exact spec/collection payload.
    Negative cases keep intentional bad bodies/query values.
    """
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    import ingester

    suite = copy.deepcopy(test_suite)
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        method = (ep.get("method") or (case.get("request") or {}).get("method") or "").upper()
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue

        category = case.get("category") or ""
        req = case.setdefault("request", {})
        ref_req = canonical_templates.build_reference_request(
            {**norm, "parameters": parameter_discovery.spec_parameters(norm)}
        )
        reference, content_type, _, _ = canonical_templates.build_reference_body(norm)

        if category in _HAPPY_CATEGORIES:
            _apply_reference_request(req, ref_req, content_type)
            if reference is not None:
                req["body"] = copy.deepcopy(reference)
            # POST/PUT must not carry query params unless declared in the spec.
            if method in BODY_METHODS:
                req["query_params"] = copy.deepcopy(ref_req.get("query_params") or {})
            continue

        if method not in BODY_METHODS:
            continue
        if reference is None:
            continue
        if not _should_inject_body(case, True):
            continue

        current = req.get("body")
        if current is None or current == {} or current == []:
            req["body"] = copy.deepcopy(reference)
        elif isinstance(current, dict) and isinstance(reference, dict):
            if not is_intentionally_empty_body_case(case):
                req["body"] = canonical_templates.merge_canonical_into_body(current, reference)

        headers = req.setdefault("headers", {})
        if content_type and not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = content_type

    return suite


def enforce_payload_expectations(test_suite: dict, norm_map: Optional[dict]) -> dict:
    """
    POST/PUT/PATCH/DELETE: happy_path uses exact reference body only.
    All other body-bearing cases expect HTTP 400.
    """
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    import ingester

    suite = copy.deepcopy(test_suite)
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        method = (ep.get("method") or (case.get("request") or {}).get("method") or "").upper()
        if method not in BODY_METHODS:
            continue

        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue

        reference, content_type, _, body_required = canonical_templates.build_reference_body(norm)
        if reference is None and not body_required:
            continue

        category = case.get("category") or ""
        req = case.setdefault("request", {})
        expected = case.setdefault("expected", {})

        if category in _HAPPY_CATEGORIES:
            ref_req = canonical_templates.build_reference_request(
                {**norm, "parameters": parameter_discovery.spec_parameters(norm)}
            )
            _apply_reference_request(req, ref_req, content_type)
            if method in BODY_METHODS:
                req["query_params"] = copy.deepcopy(ref_req.get("query_params") or {})
            continue

        if category in _SKIP_PAYLOAD_ENFORCE:
            continue

        expected["status_code"] = 400
        if category not in _NEGATIVE_BODY_CATEGORIES:
            case["category"] = "validation"

    return suite


def enforce_spec_deviation_expectations(test_suite: dict, norm_map: Optional[dict]) -> dict:
    """Any non-happy case with extra params or body mismatch expects HTTP 400."""
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    import case_normalizer
    import ingester

    suite = copy.deepcopy(test_suite)
    skip = frozenset({"happy_path", "response_schema", "auth", "rfc_semantics"})

    for case in suite.get("test_cases") or []:
        category = case.get("category") or ""
        if category in skip:
            continue
        ep = case.get("endpoint") or {}
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue
        req = case.get("request") or {}
        ref_req = case_normalizer._reference_request(norm)
        issues = case_normalizer._request_deviates(req, ref_req, norm)
        if issues:
            case_normalizer._mark_validation_400(case, issues[0])

    return suite


def body_summary_for_endpoint(norm_endpoint: Optional[dict]) -> str:
    """Short JSON preview for UI."""
    body, _, _, _ = canonical_templates.build_reference_body(norm_endpoint)
    if body is None:
        return ""
    try:
        return json.dumps(body, indent=2)[:1200]
    except TypeError:
        return str(body)[:1200]
