"""
Postman collection scripts (JavaScript) for API Forge exports.

Postman runs two script hooks per request:
  - pre-request (prerequest): runs BEFORE the HTTP call
  - post-response: runs AFTER the response returns
"""

import json
import re
from typing import Iterable, List, Optional, Set
_POSTMAN_VAR_REF = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")

# These collection variables ship with safe defaults for negative auth tests.
_VARS_WITH_DEFAULTS = frozenset({"INVALID_TOKEN", "EXPIRED_TOKEN"})


def extract_postman_var_refs(*blobs: str) -> Set[str]:
    """Find all {{VAR}} names used in serialized request fragments."""
    found = set()
    for blob in blobs:
        if not blob:
            continue
        found.update(_POSTMAN_VAR_REF.findall(blob))
    return found


def required_vars_for_request(var_refs: Iterable[str]) -> List[str]:
    """
    Variables that must be non-empty before the request runs.
    Skips INVALID_TOKEN / EXPIRED_TOKEN (collection provides test defaults).
    """
    required = []
    for name in sorted(var_refs):
        if name in _VARS_WITH_DEFAULTS:
            continue
        required.append(name)
    return required


def build_prerequest_script(required_vars: List[str], case_id: str = "") -> List[str]:
    """
    Pre-request script: aborts the request if required collection variables are unset.
    Postman will mark the request as failed and the Collection Runner moves on.
    """
    label = case_id or "request"
    vars_json = json.dumps(required_vars)

    return [
        "// API Forge — pre-request: verify collection variables",
        f"const _caseId = {json.dumps(label)};",
        f"const _required = {vars_json};",
        "const _missing = [];",
        "_required.forEach(function (name) {",
        "  const val = pm.collectionVariables.get(name);",
        "  if (val === undefined || val === null || String(val).trim() === '') {",
        "    _missing.push(name);",
        "  }",
        "});",
        "if (_missing.length) {",
        "  const msg = '[API Forge] ' + _caseId + ': set collection variables before running: ' + _missing.join(', ');",
        "  console.error(msg);",
        "  throw new Error(msg);",
        "}",
    ]


def _assertion_field_name(assertion: str) -> Optional[str]:
    quoted = re.findall(r"""['"]([^'"]+)['"]""", assertion)
    if quoted:
        return quoted[0]

    lower = assertion.lower()
    match = re.search(
        r"(?:field|key|property)\s+['\"]?([A-Za-z0-9_.-]+)['\"]?",
        lower,
    )
    if match:
        return match.group(1)

    match = re.search(
        r"(?:contains|includes|has)\s+['\"]?([A-Za-z0-9_.-]+)['\"]?",
        lower,
    )
    return match.group(1) if match else None


def _js_has_key_helper() -> List[str]:
    return [
        "function _jsonHasKey(data, key) {",
        "  if (data === null || data === undefined) return false;",
        "  if (typeof data === 'object' && !Array.isArray(data)) {",
        "    if (Object.prototype.hasOwnProperty.call(data, key)) return true;",
        "    return Object.values(data).some(function (v) { return _jsonHasKey(v, key); });",
        "  }",
        "  if (Array.isArray(data)) {",
        "    return data.some(function (item) { return _jsonHasKey(item, key); });",
        "  }",
        "  return false;",
        "}",
        "function _jsonPathExists(data, path) {",
        "  if (!path || path.charAt(0) !== '$') return false;",
        "  var current = data;",
        "  var remainder = path.slice(1);",
        "  if (remainder.charAt(0) === '.') remainder = remainder.slice(1);",
        "  if (!remainder) return true;",
        "  var parts = remainder.split('.');",
        "  for (var i = 0; i < parts.length; i++) {",
        "    var part = parts[i];",
        "    var m = part.match(/^(.+)\\[(\\d+)\\]$/);",
        "    if (m) {",
        "      if (!current || !current[m[1]] || !current[m[1]][m[2]]) return false;",
        "      current = current[m[1]][m[2]];",
        "    } else if (current && Object.prototype.hasOwnProperty.call(current, part)) {",
        "      current = current[part];",
        "    } else { return false; }",
        "  }",
        "  return true;",
        "}",
    ]


def build_test_script(case: dict) -> List[str]:
    """
    Test script: asserts expected status code and common response_assertions.
    """
    expected = case.get("expected", {})
    status_code = expected.get("status_code", 200)
    case_id = case.get("id", "?")
    assertions = expected.get("response_assertions", [])

    lines = [
        "// API Forge — test script",
        *_js_has_key_helper(),
        f'pm.test("[{case_id}] status code is {status_code}", function () {{',
        f"  pm.response.to.have.status({status_code});",
        "});",
    ]

    for idx, assertion in enumerate(assertions or []):
        if isinstance(assertion, dict):
            atype = assertion.get("type")
            if atype == "jsonpath_exists":
                path = json.dumps(assertion.get("path", "$"))
                lines.extend([
                    "",
                    f'pm.test("[{case_id}] jsonpath exists {path}", function () {{',
                    "  const body = pm.response.json();",
                    f"  pm.expect(_jsonPathExists(body, {path})).to.be.true;",
                    "});",
                ])
            elif atype == "max_response_ms":
                limit = int(assertion.get("value", 0))
                lines.extend([
                    "",
                    f'pm.test("[{case_id}] response under {limit}ms", function () {{',
                    f"  pm.expect(pm.response.responseTime).to.be.below({limit});",
                    "});",
                ])
            elif atype == "header_equals":
                name = json.dumps(str(assertion.get("name", "")))
                fragment = json.dumps(str(assertion.get("contains", "")))
                lines.extend([
                    "",
                    f'pm.test("[{case_id}] header check", function () {{',
                    f"  pm.expect(pm.response.headers.get({name})).to.include({fragment});",
                    "});",
                ])
            continue

        if not isinstance(assertion, str) or not assertion.strip():
            continue
        safe_label = assertion.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        lower = assertion.lower()

        if "valid json" in lower:
            lines.extend([
                "",
                f'pm.test("[{case_id}] assertion {idx + 1}: valid JSON", function () {{',
                "  pm.response.to.be.json;",
                "});",
            ])
            continue

        if "not empty" in lower:
            lines.extend([
                "",
                f'pm.test("[{case_id}] assertion {idx + 1}: non-empty body", function () {{',
                "  pm.expect(pm.response.text()).to.not.be.empty;",
                "});",
            ])
            continue

        field = _assertion_field_name(assertion)
        if field:
            field_json = json.dumps(field)
            lines.extend([
                "",
                f'pm.test("[{case_id}] assertion {idx + 1}: {safe_label}", function () {{',
                "  const body = pm.response.json();",
                f"  pm.expect(_jsonHasKey(body, {field_json})).to.be.true;",
                "});",
            ])
            continue

        lines.extend([
            "",
            f"// Unmapped assertion — verify manually: {safe_label}",
        ])

    return lines


def collection_prerequest_script() -> List[str]:
    """
    Collection-level pre-request: always runs before every request in the collection.
    Ensures BASE_URL is configured (minimum bar for any run).
    """
    return [
        "// API Forge — collection pre-request",
        "const baseUrl = pm.collectionVariables.get('BASE_URL');",
        "if (!baseUrl || String(baseUrl).trim() === '') {",
        "  throw new Error('[API Forge] Set BASE_URL in Collection Variables before running.');",
        "}",
    ]


def collection_test_script() -> List[str]:
    """
    Collection-level test: runs after every request; logs pass/fail for the runner summary.
    """
    return [
        "// API Forge — collection test (logging)",
        "const name = pm.info.requestName || 'request';",
        "if (pm.response.code) {",
        "  console.log('[API Forge] ' + name + ' → HTTP ' + pm.response.code);",
        "}",
    ]


def collection_events() -> List[dict]:
    """Postman collection `event` array (collection-wide prerequest + test)."""
    return [
        {
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": collection_prerequest_script(),
            },
        },
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": collection_test_script(),
            },
        },
    ]


def request_events(case: dict, required_vars: List[str]) -> List[dict]:
    """Per-request `event` array: variable guard + status assertion."""
    case_id = case.get("id", "?")
    events = []

    if required_vars:
        events.append({
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": build_prerequest_script(required_vars, case_id),
            },
        })

    events.append({
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": build_test_script(case),
        },
    })

    return events
