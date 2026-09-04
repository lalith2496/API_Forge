"""Invalid query/path parameter value test cases — always expect HTTP 400."""

from __future__ import annotations

import copy
from typing import Optional

import canonical_templates
import id_cases
import ingester
import parameter_discovery

EXPECTED_STATUS = 400

INVALID_STRING = "___INVALID_VALUE___"
MALFORMED_VALUE = "!!!@@@invalid@@@!!!"


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _suite_has_value_case(suite: dict, ep_t: tuple[str, str], param_name: str, variant: str) -> bool:
    token = f"invalid_value:{param_name}:{variant}".lower()
    for case in suite.get("test_cases") or []:
        ep = case.get("endpoint") or {}
        if _endpoint_tuple(ep) != ep_t:
            continue
        notes = (case.get("notes") or "").lower()
        if token in notes:
            return True
    return False


def _set_param(request: dict, location: str, name: str, value: str) -> None:
    if location == "path":
        request["path_params"] = dict(request.get("path_params") or {})
        request["path_params"][name] = value
    else:
        request["query_params"] = dict(request.get("query_params") or {})
        request["query_params"][name] = value


def _make_case(endpoint, description, request, param_name, variant, case_id):
    return {
        "id": case_id,
        "endpoint": {"method": endpoint["method"], "path": endpoint["path"]},
        "category": "validation",
        "description": description,
        "requires_user_input": False,
        "request": request,
        "expected": {"status_code": EXPECTED_STATUS, "response_assertions": []},
        "notes": f"Auto-generated invalid value case invalid_value:{param_name}:{variant}",
    }


def _cases_for_param(endpoint, norm, base, param, suite, ep_t, start_idx):
    out = []
    name = param.get("name")
    loc = param.get("in") or "query"
    if not name or loc not in ("query", "path"):
        return out

    schema = param.get("schema") or {}
    required = bool(param.get("required"))

    def _add(variant, description, value):
        if _suite_has_value_case(suite, ep_t, name, variant):
            return
        req = copy.deepcopy(base)
        _set_param(req, loc, name, value)
        out.append(_make_case(
            endpoint,
            description,
            req,
            name,
            variant,
            f"TC-VAL-{start_idx + len(out):02d}",
        ))

    if schema.get("type") in ("integer", "number"):
        _add(
            "wrong_type",
            f"Invalid value — non-numeric '{name}'",
            "not-a-number",
        )

    if schema.get("enum"):
        _add(
            "bad_enum",
            f"Invalid value — out-of-enum '{name}'",
            INVALID_STRING,
        )

    if required:
        _add(
            "empty_required",
            f"Invalid value — empty required '{name}'",
            "",
        )

    if id_cases.is_id_like_param(name, schema):
        bad = id_cases.BROKEN_ID_VALUES[0]
        if "ids" in name.lower():
            bad = f"{id_cases.BROKEN_ID_VALUES[0]},{id_cases.BROKEN_ID_VALUES[2]}"
        _add(
            "invalid_id",
            f"Invalid value — invalid/non-existent '{name}'",
            bad,
        )

    _add(
        "malformed",
        f"Invalid value — malformed '{name}'",
        MALFORMED_VALUE,
    )

    return out


def _spec_query_names(norm: dict) -> set[str]:
    return {
        p["name"]
        for p in parameter_discovery.spec_parameters(norm)
        if p.get("name") and (p.get("in") or "query") == "query"
    }


def _cases_for_extra_query_params(endpoint, norm, base, suite, ep_t, start_idx):
    """Add 400 cases for query params not declared in the OpenAPI spec."""
    out = []
    spec_names = _spec_query_names(norm)
    for param in parameter_discovery.testing_parameters(norm):
        if (param.get("in") or "query") != "query":
            continue
        name = param.get("name")
        if not name or name in spec_names:
            continue
        variant = f"extra_{name}"
        if _suite_has_value_case(suite, ep_t, name, variant):
            continue
        req = copy.deepcopy(base)
        req["query_params"] = dict(req.get("query_params") or {})
        req["query_params"][name] = str(param.get("example") or "extra-value")
        out.append(_make_case(
            endpoint,
            f"Invalid request — unsupported query parameter '{name}' (not in spec)",
            req,
            name,
            variant,
            f"TC-EXT-{start_idx + len(out):02d}",
        ))
    return out


def supplement_invalid_value_cases(
    test_suite: dict,
    norm_map: Optional[dict],
    base_request_fn,
) -> dict:
    """Always add invalid query/path value cases expecting HTTP 400."""
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    new_cases = []
    idx = 1

    for ep in suite.get("endpoints") or []:
        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue
        params = [
            p for p in parameter_discovery.testing_parameters(norm)
            if (p.get("in") or "query") in ("query", "path") and p.get("name")
        ]

        ep_t = _endpoint_tuple(ep)
        base = base_request_fn(ep, norm)
        for param in params:
            generated = _cases_for_param(ep, norm, base, param, suite, ep_t, idx)
            new_cases.extend(generated)
            idx += len(generated)
        extra = _cases_for_extra_query_params(ep, norm, base, suite, ep_t, idx)
        new_cases.extend(extra)
        idx += len(extra)

    if not new_cases:
        return suite

    suite["test_cases"] = (suite.get("test_cases") or []) + new_cases
    for i, case in enumerate(suite["test_cases"], start=1):
        case["id"] = f"TC-{i:02d}"
    return suite
