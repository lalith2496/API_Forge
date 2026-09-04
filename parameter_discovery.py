"""Discover query/path parameters from generated test cases and resolve norm lookups."""

from __future__ import annotations

import copy
from typing import Any, Optional

import ingester


def _endpoint_tuple(ep: dict) -> tuple[str, str]:
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def _param_key(name: str, location: str) -> tuple[str, str]:
    return (name, location)


def discover_parameters(
    norm: dict,
    suite: dict,
    ep: dict,
    imported_cases: Optional[list] = None,
) -> list[dict]:
    """
    Merge spec/import parameters with query/path keys seen in test case requests
    and imported Postman/cURL requests. Used for negative/invalid test generation only.
    """
    params = copy.deepcopy(norm.get("spec_parameters") or norm.get("parameters") or [])
    known = {
        _param_key(p.get("name", ""), p.get("in") or "query")
        for p in params
        if p.get("name")
    }
    ep_t = _endpoint_tuple(ep)

    def _add_param(name: str, location: str, value: Any, required: bool = False) -> None:
        key = _param_key(str(name), location)
        if key in known:
            for param in params:
                if param.get("name") == name and (param.get("in") or "query") == location:
                    if param.get("example") in (None, "") and value not in (None, ""):
                        param["example"] = value
            return
        params.append({
            "name": str(name),
            "in": location,
            "required": required,
            "schema": {"type": "string"},
            "example": value,
        })
        known.add(key)

    sources = list(suite.get("test_cases") or [])
    for case in imported_cases or []:
        if isinstance(case, dict):
            sources.append(case)

    for case in sources:
        case_ep = case.get("endpoint") or {}
        if _endpoint_tuple(case_ep) != ep_t:
            continue
        req = case.get("request") or {}
        for name, value in (req.get("query_params") or {}).items():
            _add_param(str(name), "query", value, required=False)
        for name, value in (req.get("path_params") or {}).items():
            _add_param(str(name), "path", value, required=True)

    return params


def spec_parameters(norm: dict) -> list[dict]:
    """Parameters declared in the OpenAPI spec / import schema only."""
    return copy.deepcopy(norm.get("spec_parameters") or norm.get("parameters") or [])


def testing_parameters(norm: dict) -> list[dict]:
    """Spec parameters plus discovered query/path keys for negative test generation."""
    return copy.deepcopy(norm.get("discovered_parameters") or spec_parameters(norm))


def norm_for_testing(norm: dict) -> dict:
    """Norm copy whose parameters include discovered keys for invalid-case generators."""
    out = copy.deepcopy(norm)
    out["parameters"] = testing_parameters(norm)
    return out


def _content_type_from_request(req: dict) -> str:
    for key, val in (req.get("headers") or {}).items():
        if key.lower() == "content-type":
            return str(val).split(";")[0].strip()
    return "application/json"


def _body_has_payload(body: Any) -> bool:
    if body is None:
        return False
    if isinstance(body, dict):
        return bool(body)
    if isinstance(body, list):
        return bool(body)
    return str(body).strip() != ""


def discover_request_body(
    suite: dict,
    ep: dict,
    imported_cases: Optional[list] = None,
) -> tuple[Any, str] | tuple[None, str]:
    """
    Find the best reference request body for an endpoint from imported cases
    or generated test cases (happy path preferred).
    """
    ep_t = _endpoint_tuple(ep)
    method = str(ep.get("method", "GET")).upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None, "application/json"

    candidates: list[tuple[int, int, Any, str]] = []
    sources: list[dict] = []
    for case in imported_cases or []:
        if isinstance(case, dict):
            sources.append(case)
    for case in suite.get("test_cases") or []:
        if isinstance(case, dict):
            sources.append(case)

    for case in sources:
        if _endpoint_tuple(case.get("endpoint") or {}) != ep_t:
            continue
        req = case.get("request") or {}
        body = req.get("body")
        if not _body_has_payload(body):
            continue
        category = case.get("category") or ""
        priority = 0 if category in {"happy_path", "response_schema"} else 1
        happy_rank = 0 if category == "happy_path" else 1
        candidates.append((priority, happy_rank, copy.deepcopy(body), _content_type_from_request(req)))

    if not candidates:
        return None, "application/json"

    candidates.sort(key=lambda item: (item[0], item[1]))
    _, _, body, content_type = candidates[0]
    return body, content_type


def _attach_reference_body(norm: dict, body: Any, content_type: str = "application/json") -> dict:
    """Merge a discovered/imported body into norm requestBody as the reference example."""
    if not _body_has_payload(body):
        return norm

    out = copy.deepcopy(norm)
    rb = copy.deepcopy(out.get("requestBody") or {})
    content = copy.deepcopy(rb.get("content") or {})
    media = copy.deepcopy(content.get(content_type) or {})
    if media.get("example") is None:
        media["example"] = copy.deepcopy(body)
    if not media.get("schema") and isinstance(body, dict):
        media["schema"] = {
            "type": "object",
            "properties": {k: {"type": "string"} for k in body},
        }
    content[content_type] = media
    out["requestBody"] = {
        "required": rb.get("required", True),
        "content": content,
    }
    out["_reference_body"] = copy.deepcopy(body)
    out["_reference_content_type"] = content_type
    return out


def _merge_imported_request_body(
    norm: dict,
    ep: dict,
    imported_cases: Optional[list],
    suite: Optional[dict] = None,
) -> dict:
    """Attach request body example from imported/generated cases when spec omits it."""
    method = str(ep.get("method", "GET")).upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return norm

    body, content_type = discover_request_body(suite or {}, ep, imported_cases=imported_cases)
    if body is None:
        return norm

    return _attach_reference_body(norm, body, content_type)


def build_effective_norm_map(
    suite: dict,
    norm_map: Optional[dict],
    imported_cases: Optional[list] = None,
) -> dict:
    """
    Resolve norm entries for suite endpoints (handles operationId key mismatch).
    Keeps spec-only parameters for happy path; stores discovered params separately.
    """
    if not norm_map or not isinstance(suite, dict):
        return norm_map or {}

    effective = dict(norm_map)
    seen_ep_t: set[tuple[str, str]] = set()

    for ep in suite.get("endpoints") or []:
        ep_t = _endpoint_tuple(ep)
        if ep_t in seen_ep_t:
            continue
        seen_ep_t.add(ep_t)

        norm = ingester.lookup_norm(norm_map, ep)
        if not norm:
            continue

        enriched = copy.deepcopy(norm)
        enriched = _merge_imported_request_body(
            enriched, ep, imported_cases, suite=suite
        )
        spec_params = copy.deepcopy(enriched.get("parameters") or norm.get("parameters") or [])
        enriched["spec_parameters"] = spec_params
        enriched["parameters"] = spec_params
        enriched["discovered_parameters"] = discover_parameters(
            enriched, suite, ep, imported_cases=imported_cases
        )

        for key in ingester.norm_lookup_keys(ep, norm_map):
            effective[key] = enriched

        base = f"{ep['method']}:{ep['path']}"
        effective[base] = enriched
        effective[ingester.endpoint_key(ep)] = enriched

    return effective
