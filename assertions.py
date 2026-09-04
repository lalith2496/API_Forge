"""
Evaluate LLM-generated response_assertions against HTTP responses.

Supports natural-language strings and structured assertion objects.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import rfc_assertions


def _parse_json(body: Optional[str]) -> tuple[Optional[Any], Optional[str]]:
    if not body or not str(body).strip():
        return None, "empty response body"
    try:
        return json.loads(body), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def _has_key(data: Any, key: str) -> bool:
    if isinstance(data, dict):
        return key in data
    if isinstance(data, list):
        return any(_has_key(item, key) for item in data)
    return False


def _extract_quoted(text: str) -> list[str]:
    return re.findall(r"""['"]([^'"]+)['"]""", text)


def _extract_field_name(text: str) -> Optional[str]:
    quoted = _extract_quoted(text)
    if quoted:
        return quoted[0]

    lower = text.lower()
    patterns = [
        r"(?:field|key|property)\s+['\"]?([A-Za-z0-9_.-]+)['\"]?",
        r"['\"]([A-Za-z0-9_.-]+)['\"]\s+(?:field|key|property)",
        r"contains\s+field\s+['\"]?([A-Za-z0-9_.-]+)['\"]?",
        r"['\"]([A-Za-z0-9_.-]+)['\"]\s+(?:exists|present|in response)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            return match.group(1)
    return None


def jsonpath_resolve(data: Any, path: str) -> tuple[bool, Any]:
    """
    Resolve a minimal JSONPath ($.a.b, $.items[0].id). Returns (found, value).
    """
    if not path or not path.startswith("$"):
        return False, None

    current = data
    remainder = path[1:]
    if remainder.startswith("."):
        remainder = remainder[1:]

    if not remainder:
        return True, current

    tokens = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)|(\[\d+\])", remainder)
    for name_match, index_match in tokens:
        if index_match:
            idx = int(index_match[1:-1])
            if not isinstance(current, list) or idx >= len(current):
                return False, None
            current = current[idx]
        elif name_match:
            if not isinstance(current, dict) or name_match not in current:
                return False, None
            current = current[name_match]

    return True, current


def evaluate_structured_assertion(
    assertion: dict,
    response_body: Optional[str],
    status_code: Optional[int] = None,
    response_headers: Optional[dict] = None,
    response_time_ms: Optional[int] = None,
) -> tuple[bool, str]:
    """Evaluate a structured assertion dict."""
    atype = assertion.get("type", "")
    label = json.dumps(assertion, sort_keys=True)

    if atype == "max_response_ms":
        limit = assertion.get("value")
        if response_time_ms is None:
            return False, f"{label}: no response time recorded"
        if response_time_ms > int(limit):
            return False, f"{label}: {response_time_ms}ms exceeds {limit}ms"
        return True, label

    if atype == "header_equals":
        headers = {k.lower(): v for k, v in (response_headers or {}).items()}
        name = str(assertion.get("name", "")).lower()
        expected = assertion.get("contains") or assertion.get("value")
        actual = headers.get(name, "")
        if expected is not None and str(expected) not in str(actual):
            return False, f"{label}: header {name}={actual!r}"
        return True, label

    data, err = _parse_json(response_body)
    path = assertion.get("path", "$")

    if atype == "jsonpath_exists":
        if data is None:
            return False, f"{label}: {err}"
        found, _ = jsonpath_resolve(data, path)
        if not found:
            return False, f"{label}: path {path} not found"
        return True, label

    if atype == "jsonpath_equals":
        if data is None:
            return False, f"{label}: {err}"
        found, value = jsonpath_resolve(data, path)
        expected = assertion.get("value")
        if not found:
            return False, f"{label}: path {path} not found"
        if value != expected:
            return False, f"{label}: expected {expected!r}, got {value!r}"
        return True, label

    if atype == "jsonpath_type":
        if data is None:
            return False, f"{label}: {err}"
        found, value = jsonpath_resolve(data, path)
        expected_type = assertion.get("value", "string")
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        if not found:
            return False, f"{label}: path {path} not found"
        py_type = type_map.get(expected_type)
        if py_type and not isinstance(value, py_type):
            return False, f"{label}: expected type {expected_type}"
        return True, label

    if atype in ("jsonpath_length_min", "jsonpath_length_max"):
        if data is None:
            return False, f"{label}: {err}"
        found, value = jsonpath_resolve(data, path)
        if not found:
            return False, f"{label}: path {path} not found"
        try:
            length = len(value)  # type: ignore[arg-type]
        except TypeError:
            return False, f"{label}: value at {path} has no length"
        limit = int(assertion.get("value", 0))
        if atype == "jsonpath_length_min" and length < limit:
            return False, f"{label}: length {length} < {limit}"
        if atype == "jsonpath_length_max" and length > limit:
            return False, f"{label}: length {length} > {limit}"
        return True, label

    if atype in ("problem_json", "cookie_flags", "content_negotiation", "security_header"):
        return rfc_assertions.evaluate_rfc_assertion(
            assertion, response_body, status_code, response_headers
        )

    return False, f"{label}: unknown structured assertion type {atype!r}"


def evaluate_assertion(
    assertion: str,
    response_body: Optional[str],
    status_code: Optional[int] = None,
    response_headers: Optional[dict] = None,
    response_time_ms: Optional[int] = None,
) -> tuple[bool, str]:
    """Return (passed, message) for a single string assertion."""
    text = (assertion or "").strip()
    if not text:
        return True, "empty assertion skipped"

    lower = text.lower()

    if "valid json" in lower or "json object" in lower or "json array" in lower:
        _, err = _parse_json(response_body)
        if err:
            return False, f"{text}: {err}"
        return True, text

    if "not empty" in lower or "non-empty" in lower or "nonempty" in lower:
        if not response_body or not str(response_body).strip():
            return False, f"{text}: response body is empty"
        return True, text

    if "content-type" in lower and "json" in lower:
        headers = {k.lower(): v for k, v in (response_headers or {}).items()}
        ct = headers.get("content-type", "")
        if "json" not in ct.lower():
            return False, f"{text}: Content-Type is {ct!r}"
        return True, text

    if "response time" in lower or "within" in lower and "ms" in lower:
        ms_match = re.search(r"(\d+)\s*ms", lower)
        if ms_match and response_time_ms is not None:
            if response_time_ms > int(ms_match.group(1)):
                return False, f"{text}: took {response_time_ms}ms"
        return True, text

    field = _extract_field_name(text)
    data, err = _parse_json(response_body)
    if field and data is not None:
        if "not" in lower and ("contain" in lower or "include" in lower or "have" in lower):
            if _has_key(data, field):
                return False, f"{text}: unexpected field '{field}' present"
            return True, text
        if _has_key(data, field):
            return True, text
        return False, f"{text}: field '{field}' not found in response JSON"

    if "status" in lower and status_code is not None:
        codes = [int(m) for m in re.findall(r"\b(\d{3})\b", text)]
        if codes and status_code not in codes:
            return False, f"{text}: expected one of {codes}, got {status_code}"

    quoted = _extract_quoted(text)
    body_lower = (response_body or "").lower()
    for fragment in quoted:
        if fragment.lower() not in body_lower:
            return False, f"{text}: response does not contain '{fragment}'"

    if data is not None and err is None:
        return True, f"{text}: no specific rule matched (JSON response OK)"

    if response_body and len(response_body.strip()) > 0:
        return True, f"{text}: assumed pass (non-empty body)"

    return False, f"{text}: could not evaluate assertion"


def evaluate_assertions(
    assertions: list,
    response_body: Optional[str],
    status_code: Optional[int] = None,
    response_headers: Optional[dict] = None,
    response_time_ms: Optional[int] = None,
) -> tuple[bool, list[str]]:
    """Evaluate all assertions. Returns (all_passed, failure_messages)."""
    if not assertions:
        return True, []

    failures = []
    for assertion in assertions:
        if isinstance(assertion, dict):
            ok, msg = evaluate_structured_assertion(
                assertion,
                response_body,
                status_code,
                response_headers,
                response_time_ms,
            )
        elif isinstance(assertion, str):
            ok, msg = evaluate_assertion(
                assertion,
                response_body,
                status_code,
                response_headers,
                response_time_ms,
            )
        else:
            failures.append(f"Invalid assertion type: {type(assertion).__name__}")
            continue
        if not ok:
            failures.append(msg)

    return len(failures) == 0, failures
