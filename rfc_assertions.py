"""RFC-aware structured assertions (7807, 6265, 9110)."""

from __future__ import annotations

import json
import re
from typing import Optional


def evaluate_rfc_assertion(
    assertion: dict,
    response_body: Optional[str],
    status_code: Optional[int],
    response_headers: Optional[dict],
) -> tuple[bool, str]:
    """Evaluate RFC-specific structured assertion types."""
    atype = assertion.get("type", "")
    label = json.dumps(assertion, sort_keys=True)
    headers = {k.lower(): v for k, v in (response_headers or {}).items()}

    if atype == "problem_json":
        ct = headers.get("content-type", "")
        if "application/problem+json" not in ct and "application/json" not in ct:
            return False, f"{label}: expected problem+json Content-Type, got {ct!r}"
        try:
            data = json.loads(response_body or "{}")
        except json.JSONDecodeError as exc:
            return False, f"{label}: invalid JSON: {exc}"
        for field in ("type", "title", "status"):
            if field not in data:
                return False, f"{label}: missing RFC 7807 field '{field}'"
        if status_code is not None and data.get("status") != status_code:
            return False, f"{label}: status field {data.get('status')} != HTTP {status_code}"
        return True, label

    if atype == "cookie_flags":
        cookie_name = assertion.get("name", "")
        set_cookie = headers.get("set-cookie", "")
        if not set_cookie:
            return False, f"{label}: no Set-Cookie header"
        if cookie_name and cookie_name.lower() not in set_cookie.lower():
            return False, f"{label}: cookie {cookie_name!r} not in Set-Cookie"
        flags = set_cookie.lower()
        for flag in assertion.get("require", ("Secure", "HttpOnly")):
            if flag.lower() == "secure" and "secure" not in flags:
                return False, f"{label}: missing Secure flag"
            if flag.lower() == "httponly" and "httponly" not in flags:
                return False, f"{label}: missing HttpOnly flag"
            if flag.lower() == "samesite" and "samesite" not in flags:
                return False, f"{label}: missing SameSite flag"
        return True, label

    if atype == "content_negotiation":
        expected_ct = assertion.get("content_type", "")
        ct = headers.get("content-type", "")
        if expected_ct and expected_ct not in ct:
            return False, f"{label}: Content-Type {ct!r} != {expected_ct!r}"
        return True, label

    if atype == "security_header":
        header_name = str(assertion.get("name", "")).lower()
        if header_name and header_name not in headers:
            return False, f"{label}: missing security header {header_name!r}"
        return True, label

    return False, f"{label}: unknown RFC assertion type {atype!r}"


def default_assertions_for_category(category: str, status_code: int) -> list:
    """Suggest default RFC assertions based on test category."""
    if category == "rfc_problem" and status_code >= 400:
        return [{"type": "problem_json"}]
    if category == "rfc_cookies" and status_code < 400:
        return [{"type": "cookie_flags", "require": ["Secure", "HttpOnly"]}]
    return []


def parse_set_cookie_flags(set_cookie: str) -> dict:
    """Parse Secure/HttpOnly/SameSite from Set-Cookie header value."""
    lower = set_cookie.lower()
    return {
        "secure": "secure" in lower,
        "httponly": "httponly" in lower,
        "samesite": re.search(r"samesite=([^;]+)", lower),
    }
