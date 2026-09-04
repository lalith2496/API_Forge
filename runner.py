"""
Execute generated test cases using the requests library.
Supports parallel runs, auth injection, content-type aware bodies, and assertions.
"""

from __future__ import annotations

import copy
import ipaddress
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import user_inputs
import assertions
import auth_helpers
import schema_validator
import rfc_assertions


def validate_url(url: str) -> tuple[bool, Optional[str]]:
    """SSRF guard: block private/reserved hosts unless ALLOWED_HOSTS is set."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "Only http and https URLs are allowed"

    host = parsed.hostname
    if not host:
        return False, "Invalid URL: missing hostname"

    allowed = os.getenv("ALLOWED_HOSTS", "").strip()
    if allowed:
        allowed_hosts = {h.strip().lower() for h in allowed.split(",") if h.strip()}
        if host.lower() not in allowed_hosts:
            return False, f"Host '{host}' is not in ALLOWED_HOSTS"
        return True, None

    blocked_names = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    if host.lower() in blocked_names:
        return False, f"Requests to {host} are blocked"

    try:
        addr_info = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True, None

    for info in addr_info:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False, f"Requests to private/reserved addresses are blocked ({host} → {ip_str})"

    return True, None


def _replace(value: Any, user_vals: dict, env_vals: Optional[dict] = None) -> Any:
    env_vals = env_vals or {}

    if isinstance(value, str):
        input_vals = {**(user_vals or {}), **env_vals}
        s = user_inputs.replace_user_inputs(value, input_vals)
        if "EXPIRED_TOKEN" in s:
            s = s.replace("EXPIRED_TOKEN", str(env_vals.get("EXPIRED_TOKEN", "expired_token_for_testing")))
        if "INVALID_TOKEN" in s:
            s = s.replace("INVALID_TOKEN", str(env_vals.get("INVALID_TOKEN", "invalid_token_for_testing")))
        if "API_KEY" in s:
            s = s.replace("API_KEY", str(env_vals.get("API_KEY", "") or ""))
        if "VALID_TOKEN" in s:
            s = s.replace("VALID_TOKEN", str(env_vals.get("ACCESS_TOKEN", "") or ""))
        return s

    if isinstance(value, dict):
        return {k: _replace(val, user_vals, env_vals) for k, val in value.items()}
    if isinstance(value, list):
        return [_replace(val, user_vals, env_vals) for val in value]
    return value


def _replace_headers(
    headers: dict,
    user_vals: dict,
    env_vals: Optional[dict] = None,
    case: Optional[dict] = None,
) -> dict:
    env_vals = env_vals or {}
    out: dict = {}
    for name, value in (headers or {}).items():
        replaced = _replace(value, user_vals, env_vals)
        out[name] = auth_helpers.resolve_header_value(name, replaced, env_vals, case=case)
    return out


def merge_request_overrides(req: dict, overrides: Optional[dict]) -> dict:
    """Deep-merge per-case rerun overrides into a request dict."""
    if not overrides:
        return req
    merged = copy.deepcopy(req or {})
    if overrides.get("headers"):
        hdrs = dict(merged.get("headers") or {})
        hdrs.update(overrides["headers"])
        merged["headers"] = hdrs
    if "body" in overrides and overrides["body"] is not None:
        merged["body"] = overrides["body"]
    if overrides.get("query_params"):
        qp = dict(merged.get("query_params") or {})
        qp.update(overrides["query_params"])
        merged["query_params"] = qp
    if overrides.get("path_params"):
        pp = dict(merged.get("path_params") or {})
        pp.update(overrides["path_params"])
        merged["path_params"] = pp
    return merged


def _build_url(base_url: str, path: str, params: dict) -> str:
    url = base_url.rstrip("/") + ("/" if not path.startswith("/") else "") + path
    for key, val in (params or {}).items():
        url = url.replace("{" + key + "}", str(val))
    return url


def _content_type(headers: dict) -> str:
    for key, val in (headers or {}).items():
        if key.lower() == "content-type":
            return str(val).split(";")[0].strip().lower()
    return "application/json"


def _attach_body_kwargs(kwargs: dict, body: Any, content_type: str) -> None:
    if body is None:
        return
    if content_type == "application/x-www-form-urlencoded":
        if isinstance(body, dict):
            kwargs["data"] = body
        else:
            kwargs["data"] = body
    elif content_type.startswith("multipart/form-data"):
        if isinstance(body, dict):
            kwargs["files"] = {k: (None, str(v)) for k, v in body.items()}
        else:
            kwargs["data"] = body
    elif content_type in ("text/plain", "application/xml", "application/yaml"):
        kwargs["data"] = body if isinstance(body, str) else str(body)
    elif content_type == "application/json" and isinstance(body, str):
        kwargs["data"] = body
    else:
        kwargs["json"] = body


def _skipped_result(case: dict) -> dict:
    return {
        "id": case.get("id", "?"),
        "category": case.get("category", ""),
        "description": case.get("description", ""),
        "expected_status": (case.get("expected") or {}).get("status_code"),
        "actual_status": None,
        "passed": None,
        "response_time_ms": None,
        "error": None,
        "assertion_failures": [],
        "request_url": None,
        "response_body": None,
        "skipped": True,
    }


def run_case(
    case: dict,
    base_url: str,
    user_vals: dict,
    env_vals: Optional[dict] = None,
    timeout: int = 10,
    url_override: Optional[str] = None,
    max_response_ms: Optional[int] = None,
    norm_endpoint: Optional[dict] = None,
    param_overrides: Optional[dict] = None,
    request_overrides: Optional[dict] = None,
) -> dict:
    """Run a single test case and return a result dict."""
    req = case.get("request", {})
    expected = case.get("expected", {})
    endpoint = case.get("endpoint", {})

    req = user_inputs.apply_request_param_overrides(
        req, param_overrides, case_category=case.get("category")
    )
    req = merge_request_overrides(req, request_overrides)

    method = (req.get("method") or endpoint.get("method", "GET")).upper()
    path = _replace((req.get("path") or endpoint.get("path", "/")), user_vals, env_vals)

    headers = _replace_headers(req.get("headers") or {}, user_vals, env_vals, case=case)
    query_params = _replace(req.get("query_params") or {}, user_vals, env_vals)
    path_params = _replace(req.get("path_params") or {}, user_vals, env_vals)
    body = _replace(req.get("body"), user_vals, env_vals)

    headers = auth_helpers.apply_auth_headers(
        {k: str(v) for k, v in headers.items() if v is not None},
        case,
        env_vals,
    )
    query_params = {k: str(v) for k, v in query_params.items() if v is not None}

    url = url_override or _build_url(base_url, path, path_params)
    send_params = {} if url_override else query_params

    result = {
        "id": case.get("id", "?"),
        "category": case.get("category", "default"),
        "description": case.get("description", "default desc"),
        "expected_status": expected.get("status_code"),
        "actual_status": None,
        "passed": False,
        "response_time_ms": 0,
        "error": None,
        "assertion_failures": [],
        "request_url": url,
        "request": {
            "method": method,
            "url": url,
            "headers": headers,
            "query_params": send_params,
            "path_params": path_params,
            "body": body,
        },
        "response_body": None,
        "response_headers": {},
        "skipped": False,
    }

    url_ok, url_err = validate_url(url)
    if not url_ok:
        result["error"] = url_err
        return result

    try:
        import requests

        kwargs: dict = {"headers": headers, "timeout": timeout, "params": send_params}
        _attach_body_kwargs(kwargs, body, _content_type(headers))

        t_init = time.perf_counter()
        result["request_url"] = requests.Request(method, url, params=send_params).prepare().url
        result["request"]["url"] = result["request_url"]
        resp = requests.request(method, url, **kwargs)
        elapsed = time.perf_counter() - t_init

        result["actual_status"] = resp.status_code
        result["response_time_ms"] = round(elapsed * 1000)
        result["request_url"] = resp.url
        result["request"]["url"] = resp.url
        result["response_headers"] = dict(resp.headers)

        body_text = resp.text
        result["response_body"] = body_text[:2000] + ("..." if len(body_text) > 2000 else "")

        status_ok = expected.get("status_code") == resp.status_code
        assertion_list = list(expected.get("response_assertions") or [])

        default_rfc = rfc_assertions.default_assertions_for_category(
            case.get("category", ""),
            resp.status_code,
        )
        for item in default_rfc:
            if item not in assertion_list:
                assertion_list.append(item)

        if max_response_ms and result["response_time_ms"] > max_response_ms:
            assertion_list = assertion_list + [
                {"type": "max_response_ms", "value": max_response_ms}
            ]

        if norm_endpoint and case.get("category") in ("happy_path", "response_schema"):
            schema = schema_validator.response_schema_for_status(
                norm_endpoint,
                expected.get("status_code") or resp.status_code,
            )
            if schema and body_text:
                data, _ = assertions._parse_json(body_text)
                if data is not None:
                    ok_schema, schema_errors = schema_validator.validate_against_schema(data, schema)
                    if not ok_schema:
                        assertion_list = assertion_list + [
                            f"schema validation: {err}" for err in schema_errors[:5]
                        ]

        assertions_ok, assertion_failures = assertions.evaluate_assertions(
            assertion_list,
            body_text,
            resp.status_code,
            result["response_headers"],
            result["response_time_ms"],
        )
        result["assertion_failures"] = assertion_failures
        result["passed"] = status_ok and assertions_ok

        if not status_ok and not result["error"]:
            result["error"] = (
                f"Expected status {expected.get('status_code')}, got {resp.status_code}"
            )
        elif status_ok and not assertions_ok:
            result["error"] = "; ".join(assertion_failures)

    except Exception as exc:
        if exc.__class__.__name__ == "ConnectionError":
            result["error"] = "Connection refused or DNS failure"
        elif exc.__class__.__name__ == "Timeout":
            result["error"] = f"Timed out after {timeout}s"
        else:
            result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def _resolve_norm_endpoint(case: dict, norm_map: Optional[dict]) -> Optional[dict]:
    if not norm_map:
        return None
    import ingester
    ep = case.get("endpoint") or {}
    return ingester.lookup_norm(norm_map, ep)


def run_cases(
    suite: dict,
    base_url: str,
    user_vals: dict,
    env_vals: Optional[dict] = None,
    timeout: int = 10,
    skip_rate_limit: bool = True,
    concurrency: int = 5,
    categories_filter: Optional[list[str]] = None,
    max_response_ms: Optional[int] = None,
    norm_map: Optional[dict] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    param_overrides: Optional[dict] = None,
    request_overrides_by_id: Optional[dict[str, dict]] = None,
) -> list[dict]:
    """Run the whole suite; optional parallel execution and category filter."""
    base_ok, base_err = validate_url(base_url.strip()) if base_url.strip() else (False, "Base URL is empty")
    if not base_ok:
        return [{
            "id": "?",
            "category": "",
            "description": "Base URL validation failed",
            "expected_status": None,
            "actual_status": None,
            "passed": False,
            "response_time_ms": 0,
            "error": base_err,
            "assertion_failures": [],
            "request_url": base_url,
            "response_body": None,
            "skipped": False,
        }]

    cases = suite.get("test_cases", [])
    filter_set = set(categories_filter) if categories_filter else None
    work: list[tuple[int, dict]] = []

    for idx, case in enumerate(cases):
        if skip_rate_limit and case.get("category") == "rate_limit":
            continue
        if filter_set and case.get("category") not in filter_set:
            continue
        work.append((idx, case))

    results_by_idx: dict[int, dict] = {}
    skipped_indices: dict[int, dict] = {}

    for idx, case in enumerate(cases):
        if skip_rate_limit and case.get("category") == "rate_limit":
            skipped_indices[idx] = _skipped_result(case)
        elif filter_set and case.get("category") not in filter_set:
            skipped_indices[idx] = _skipped_result(case)

    if not work:
        return list(skipped_indices.values())

    concurrency = max(1, min(int(concurrency or 1), 10))

    def _run_one(item: tuple[int, dict]) -> tuple[int, dict]:
        idx, case = item
        norm_ep = _resolve_norm_endpoint(case, norm_map)
        return idx, run_case(
            case,
            base_url,
            user_vals,
            env_vals,
            timeout,
            max_response_ms=max_response_ms,
            norm_endpoint=norm_ep,
            param_overrides=param_overrides,
            request_overrides=(request_overrides_by_id or {}).get(case.get("id")),
        )

    completed = 0
    total = len(work)

    if concurrency <= 1:
        for item in work:
            idx, res = _run_one(item)
            results_by_idx[idx] = res
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(_run_one, item): item[0] for item in work}
            for future in as_completed(futures):
                idx, res = future.result()
                results_by_idx[idx] = res
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

    ordered: list[dict] = []
    for idx in range(len(cases)):
        if idx in skipped_indices:
            ordered.append(skipped_indices[idx])
        elif idx in results_by_idx:
            ordered.append(results_by_idx[idx])

    return ordered


def stats(results: list[dict]) -> dict:
    """Count pass, fail, error, skipped."""
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed") is True),
        "failed": sum(
            1 for r in results
            if r.get("passed") is False and not r.get("skipped") and not r.get("error")
        ),
        "error": sum(1 for r in results if r.get("error")),
        "skipped": sum(1 for r in results if r.get("skipped")),
    }


def category_coverage(suite: dict) -> dict[str, int]:
    """Count test cases per category in a suite."""
    counts: dict[str, int] = {}
    for case in suite.get("test_cases", []):
        cat = case.get("category") or "unknown"
        counts[cat] = counts.get(cat, 0) + 1
    return counts
