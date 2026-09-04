"""Invalid request payload test cases — always expect HTTP 400."""

from __future__ import annotations

import copy
from typing import Any, Optional

import canonical_templates
import ingester

BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
EXPECTED_STATUS = 400


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _has_request_body(norm: dict) -> bool:
    rb = norm.get("requestBody")
    return bool(rb and isinstance(rb, dict) and rb.get("content"))


def _suite_has_payload_case(suite: dict, ep_t: tuple[str, str], variant: str) -> bool:
    token = f"invalid_payload:{variant}".lower()
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        if _endpoint_tuple(ep) != ep_t:
            continue
        notes = (case.get("notes") or "").lower()
        desc = (case.get("description") or "").lower()
        if token in notes:
            return True
        if "invalid payload" in desc and variant.replace("_", " ") in desc:
            return True
    return False


def _make_case(endpoint, description, request, variant, case_id):
    return {
        "id": case_id,
        "endpoint": {"method": endpoint["method"], "path": endpoint["path"]},
        "category": "validation",
        "description": description,
        "requires_user_input": False,
        "request": request,
        "expected": {"status_code": EXPECTED_STATUS, "response_assertions": []},
        "notes": f"Auto-generated invalid payload case invalid_payload:{variant}",
    }


def _wrong_type_value(field: dict) -> Any:
    ftype = field.get("type", "string")
    if ftype == "string":
        return 12345
    if ftype in ("integer", "number"):
        return "not-a-number"
    if ftype == "boolean":
        return "not-a-boolean"
    if ftype == "array":
        return {"not": "array"}
    if ftype == "object":
        return "not-an-object"
    return None


def _cases_for_endpoint(endpoint, norm, base, suite, ep_t, start_idx):
    out = []
    body, content_type, field_meta, body_required = canonical_templates.build_canonical_body(norm)
    reference, _, _, _ = canonical_templates.build_reference_body(norm)
    if reference is not None:
        body = reference
    if body is None and not body_required:
        return out

    def _add(variant, description, request):
        if _suite_has_payload_case(suite, ep_t, variant):
            return
        out.append(_make_case(
            endpoint,
            description,
            request,
            variant,
            f"TC-PAY-{start_idx + len(out):02d}",
        ))

    if isinstance(body, dict) and body:
        required = [f for f in field_meta if f.get("required")]
        if not required:
            required = field_meta[:1]

        for field in required[:3]:
            fpath = field.get("path", field.get("name", ""))
            fname = field.get("name", fpath)

            req = copy.deepcopy(base)
            req["body"] = canonical_templates.remove_field_key(body, fpath)
            _add(
                f"missing_{fname}",
                f"Invalid payload — missing required field '{fname}'",
                req,
            )

            req = copy.deepcopy(base)
            req["body"] = canonical_templates.mutate_field_value(body, fpath, _wrong_type_value(field))
            _add(
                f"wrong_type_{fname}",
                f"Invalid payload — wrong type for field '{fname}'",
                req,
            )

            req = copy.deepcopy(base)
            req["body"] = canonical_templates.mutate_field_value(body, fpath, None)
            _add(
                f"null_{fname}",
                f"Invalid payload — null value for required field '{fname}'",
                req,
            )

            if field.get("enum"):
                req = copy.deepcopy(base)
                req["body"] = canonical_templates.mutate_field_value(
                    body, fpath, "___INVALID_ENUM___"
                )
                _add(
                    f"bad_enum_{fname}",
                    f"Invalid payload — invalid enum for '{fname}'",
                    req,
                )

        if body_required:
            req = copy.deepcopy(base)
            req["body"] = {}
            _add("empty_body", "Invalid payload — empty body when required", req)

        req = copy.deepcopy(base)
        headers = dict(req.get("headers") or {})
        headers["Content-Type"] = content_type or "application/json"
        req["headers"] = headers
        req["body"] = '{"invalid": json syntax'
        _add("malformed_json", "Invalid payload — malformed JSON body", req)

    elif body_required:
        req = copy.deepcopy(base)
        req["body"] = None
        _add("missing_body", "Invalid payload — missing request body", req)

    method = endpoint.get("method", "GET").upper()
    if method == "GET" and not _has_request_body(norm):
        req = copy.deepcopy(base)
        req["headers"] = dict(req.get("headers") or {})
        req["headers"]["Content-Type"] = "application/json"
        req["body"] = {"unexpectedPayload": True}
        _add("unexpected_get_body", "Invalid payload — unexpected body on GET request", req)

    return out


def supplement_invalid_payload_cases(
    test_suite: dict,
    norm_map: Optional[dict],
    base_request_fn,
) -> dict:
    """Always add invalid payload validation cases expecting HTTP 400."""
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    new_cases = []
    idx = 1

    for ep in suite.get("endpoints") or []:
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue
        method = ep.get("method", "GET").upper()
        if method not in BODY_METHODS and not _has_request_body(norm):
            if method != "GET":
                continue

        ep_t = _endpoint_tuple(ep)
        base = base_request_fn(ep, norm)
        generated = _cases_for_endpoint(ep, norm, base, suite, ep_t, idx)
        new_cases.extend(generated)
        idx += len(generated)

    if not new_cases:
        return suite

    suite["test_cases"] = (suite.get("test_cases") or []) + new_cases
    for i, case in enumerate(suite["test_cases"], start=1):
        case["id"] = f"TC-{i:02d}"
    return suite
