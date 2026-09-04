"""Generate validation/boundary edge cases from normalized endpoint metadata."""

from __future__ import annotations

import copy
from typing import Any, Optional

import ingester
import spec_bodies
import canonical_templates
import parameter_discovery
import id_cases

_NEGATIVE_CATEGORIES = frozenset({"validation", "boundary", "auth", "optional_fields"})


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _pick_error_status(norm: dict, preferred: tuple[str, ...] = ("400", "422", "401", "403", "404")) -> int:
    responses = norm.get("responses") or {}
    for code in preferred:
        if code in responses:
            return int(code)
    return int(preferred[0])


def _existing_negative_keys(suite: dict) -> set[tuple[str, str, str]]:
    """Track (method, path, category+description slug) already present."""
    keys = set()
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        cat = case.get("category") or ""
        if cat in _NEGATIVE_CATEGORIES:
            desc = (case.get("description") or "")[:40].lower()
            keys.add((*_endpoint_tuple(ep), cat, desc))
    return keys


def _base_request(endpoint: dict, norm: dict) -> dict:
    req = canonical_templates.build_reference_request(parameter_discovery.norm_for_testing(norm))
    req.pop("_field_meta", None)
    return req


def _make_case(
    endpoint: dict,
    category: str,
    description: str,
    request: dict,
    status_code: int,
    case_id: str,
) -> dict:
    return {
        "id": case_id,
        "endpoint": {"method": endpoint["method"], "path": endpoint["path"]},
        "category": category,
        "description": description,
        "requires_user_input": False,
        "request": request,
        "expected": {"status_code": status_code, "response_assertions": []},
        "notes": "Auto-generated edge case from API spec",
    }


def _cases_for_endpoint(
    endpoint: dict,
    norm: dict,
    start_idx: int,
    existing: set[tuple],
) -> list[dict]:
    out: list[dict] = []
    method = endpoint["method"]
    path = endpoint["path"]
    ep_t = _endpoint_tuple(endpoint)

    def _add(category: str, description: str, request: dict, status: int) -> None:
        key = (*ep_t, category, description[:40].lower())
        if key in existing:
            return
        existing.add(key)
        out.append(
            _make_case(
                endpoint,
                category,
                description,
                request,
                status,
                f"TC-AUTO-{start_idx + len(out):02d}",
            )
        )

    base = _base_request(endpoint, norm)

    if norm.get("security"):
        no_auth = copy.deepcopy(base)
        no_auth["headers"] = {
            k: v for k, v in (no_auth.get("headers") or {}).items()
            if k.lower() != "authorization"
        }
        _add(
            "auth",
            "Missing Authorization header",
            no_auth,
            _pick_error_status(norm, ("401", "403", "400")),
        )
        invalid_auth = copy.deepcopy(base)
        invalid_auth["headers"] = dict(invalid_auth.get("headers") or {})
        invalid_auth["headers"]["Authorization"] = "Bearer INVALID_TOKEN"
        _add(
            "auth",
            "Invalid bearer token",
            invalid_auth,
            _pick_error_status(norm, ("401", "403", "400")),
        )

    for param in norm.get("parameters") or []:
        if param.get("in") != "query" or not param.get("required"):
            continue
        name = param["name"]
        req = copy.deepcopy(base)
        qp = dict(req.get("query_params") or {})
        qp.pop(name, None)
        req["query_params"] = qp
        _add(
            "validation",
            f"Missing required query parameter '{name}'",
            req,
            _pick_error_status(norm, ("400", "422", "404")),
        )

        schema = param.get("schema") or {}
        if schema.get("type") in ("integer", "number"):
            bad = copy.deepcopy(base)
            bad_qp = dict(bad.get("query_params") or {})
            bad_qp[name] = "not-a-number"
            bad["query_params"] = bad_qp
            _add(
                "boundary",
                f"Invalid type for query parameter '{name}'",
                bad,
                _pick_error_status(norm, ("400", "422")),
            )
        if schema.get("enum"):
            bad = copy.deepcopy(base)
            bad_qp = dict(bad.get("query_params") or {})
            bad_qp[name] = "___INVALID_ENUM___"
            bad["query_params"] = bad_qp
            _add(
                "boundary",
                f"Out-of-enum value for query parameter '{name}'",
                bad,
                _pick_error_status(norm, ("400", "422")),
            )

        if id_cases.is_id_like_param(name, schema):
            bad = copy.deepcopy(base)
            bad_qp = dict(bad.get("query_params") or {})
            val = id_cases.BROKEN_ID_VALUES[0]
            if "ids" in name.lower():
                val = f"{id_cases.BROKEN_ID_VALUES[0]},{id_cases.BROKEN_ID_VALUES[2]}"
            bad_qp[name] = val
            bad["query_params"] = bad_qp
            _add(
                "validation",
                f"Invalid/non-existent '{name}' for retrieval",
                bad,
                _pick_error_status(norm, ("404", "400", "422")),
            )

    for param in norm.get("parameters") or []:
        if param.get("in") != "path":
            continue
        name = param["name"]
        schema = param.get("schema") or {}
        if id_cases.is_id_like_param(name, schema):
            bad = copy.deepcopy(base)
            bad_pp = dict(bad.get("path_params") or {})
            bad_pp[name] = id_cases.BROKEN_ID_VALUES[0]
            bad["path_params"] = bad_pp
            _add(
                "validation",
                f"Invalid/non-existent path '{name}' for retrieval",
                bad,
                _pick_error_status(norm, ("404", "400", "422")),
            )

    body, _, field_meta, body_required = canonical_templates.build_canonical_body(norm)
    if body is not None and isinstance(body, dict) and body:
        schema_required = {f["name"] for f in field_meta if f.get("required")}

        field_to_drop = next(iter(schema_required or body.keys()), None)
        if field_to_drop:
            bad_body = copy.deepcopy(base)
            bad_body["body"] = canonical_templates.remove_field_key(body, field_to_drop)
            _add(
                "validation",
                f"Missing required body field '{field_to_drop}'",
                bad_body,
                _pick_error_status(norm, ("400", "422")),
            )

        if body_required:
            empty_shape = copy.deepcopy(base)
            empty_shape["body"] = canonical_templates.mutate_field_value(
                body, next(iter(body.keys()), ""), ""
            ) if body else {}
            _add(
                "validation",
                "Invalid empty value for required body field",
                empty_shape,
                _pick_error_status(norm, ("400", "422")),
            )

        first_field = field_meta[0] if field_meta else None
        if first_field:
            wrong_type = copy.deepcopy(base)
            wrong_type["body"] = canonical_templates.mutate_field_value(
                body, first_field["path"], ["invalid", "array", "type"]
            )
            _add(
                "boundary",
                f"Wrong type for body field '{first_field['path']}'",
                wrong_type,
                _pick_error_status(norm, ("400", "422")),
            )

    if method == "GET" and not (norm.get("parameters") or []):
        bad = copy.deepcopy(base)
        bad["query_params"] = dict(bad.get("query_params") or {})
        bad["query_params"]["__forge_invalid_param__"] = "x" * 500
        _add(
            "boundary",
            "Oversized query string value",
            bad,
            _pick_error_status(norm, ("400", "414", "422", "404")),
        )

    return out


def supplement_negative_cases(
    test_suite: dict,
    norm_map: Optional[dict],
    min_negative_per_endpoint: int = 2,
) -> dict:
    """
    Add spec-driven validation/boundary/auth cases when the LLM under-generated them.
    """
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    existing = _existing_negative_keys(suite)

    counts: dict[tuple[str, str], int] = {}
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        cat = case.get("category") or ""
        if cat in _NEGATIVE_CATEGORIES:
            t = _endpoint_tuple(ep)
            counts[t] = counts.get(t, 0) + 1

    auto_cases: list[dict] = []
    auto_idx = 1

    for ep in suite.get("endpoints") or []:
        ep_t = _endpoint_tuple(ep)
        if counts.get(ep_t, 0) >= min_negative_per_endpoint:
            continue
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue
        generated = _cases_for_endpoint(ep, norm, auto_idx, existing)
        auto_cases.extend(generated)
        auto_idx += len(generated)

    if not auto_cases:
        return suite

    suite["test_cases"] = (suite.get("test_cases") or []) + auto_cases
    for idx, case in enumerate(suite["test_cases"], start=1):
        case["id"] = f"TC-{idx:02d}"

    return suite
