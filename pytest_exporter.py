import base64
import json
import textwrap

from user_inputs import (
    build_user_input_env_lines,
    extract_user_input_fields,
    field_to_env_key,
)

# Template uses {{BRACE}} tokens — no f-string, so dict literals stay valid.
_PYTEST_TEMPLATE = r"""\
import base64
import json
import os
import re
import requests
import pytest
from dotenv import load_dotenv

load_dotenv()

_SUITE_B64 = __SUITE_B64__
SUITE = json.loads(base64.b64decode(_SUITE_B64).decode("utf-8"))

BASE_URL = os.getenv("API_BASE_URL", "").strip()
__AUTH_ENV_BLOCK__

__USER_INPUT_BLOCK__

_USER_INPUT_RE = re.compile(r"USER_INPUT[:_]([A-Za-z0-9_-]+)")


def replace_placeholders(value):
    if isinstance(value, str):
        def _sub_user_input(match):
            name = match.group(1)
            resolved = USER_INPUT_VALUES.get(name, "")
            return resolved if resolved else match.group(0)

        value = _USER_INPUT_RE.sub(_sub_user_input, value)
        if "EXPIRED_TOKEN" in value:
            value = value.replace("EXPIRED_TOKEN", EXPIRED_TOKEN)
        if "INVALID_TOKEN" in value:
            value = value.replace("INVALID_TOKEN", INVALID_TOKEN)
        if "VALID_TOKEN" in value:
            value = value.replace("VALID_TOKEN", ACCESS_TOKEN)
        return value
    if isinstance(value, list):
        return [replace_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_placeholders(item) for key, item in value.items()}
    return value


def _unresolved_user_inputs(case):
    blob = json.dumps(case.get("request", {}))
    if "USER_INPUT" not in blob:
        return []
    return [
        name for name in sorted({m.group(1) for m in _USER_INPUT_RE.finditer(blob)})
        if not USER_INPUT_VALUES.get(name)
    ]


def _json_has_key(data, key):
    if isinstance(data, dict):
        if key in data:
            return True
        return any(_json_has_key(v, key) for v in data.values())
    if isinstance(data, list):
        return any(_json_has_key(item, key) for item in data)
    return False


def _check_assertions(case, response):
    for assertion in (case.get("expected") or {}).get("response_assertions") or []:
        if isinstance(assertion, dict):
            atype = assertion.get("type")
            if atype == "max_response_ms":
                limit = int(assertion.get("value", 0))
                elapsed = response.elapsed.total_seconds() * 1000
                assert elapsed <= limit, f"response took {elapsed:.0f}ms > {limit}ms"
            elif atype == "header_equals":
                name = str(assertion.get("name", "")).lower()
                expected = assertion.get("contains") or assertion.get("value")
                actual = response.headers.get(name, "")
                assert str(expected) in str(actual), f"header {name}={actual!r}"
            elif atype == "jsonpath_exists":
                body = response.json()
                path = assertion.get("path", "$")
                ok, _ = _jsonpath_resolve(body, path)
                assert ok, f"path {path} not found"
            elif atype == "jsonpath_equals":
                body = response.json()
                path = assertion.get("path", "$")
                ok, val = _jsonpath_resolve(body, path)
                assert ok and val == assertion.get("value"), f"path {path} mismatch"
            continue
        if not isinstance(assertion, str):
            continue
        lower = assertion.lower()
        if "valid json" in lower:
            try:
                response.json()
            except Exception:
                pytest.fail(assertion + ": response is not valid JSON")
        match = re.search(
            r"(?:field|key|contains|has|includes)\s+['\"]?([A-Za-z0-9_.-]+)",
            lower,
        )
        if match:
            try:
                body = response.json()
            except Exception:
                pytest.fail(assertion + ": expected JSON response")
            if not _json_has_key(body, match.group(1)):
                pytest.fail(assertion + ": field '" + match.group(1) + "' not found")
        if "not empty" in lower and not (response.text or "").strip():
            pytest.fail(assertion + ": response body is empty")


def _jsonpath_resolve(data, path):
    if not path or not str(path).startswith("$"):
        return False, None
    current = data
    remainder = str(path)[1:]
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


def build_url(path, path_params, template_path):
    resolved = replace_placeholders(path or template_path)
    for key, val in (path_params or {}).items():
        resolved = resolved.replace("{" + key + "}", str(val))
    if not BASE_URL:
        raise ValueError(
            "API_BASE_URL is not set. Add it to your .env file before running tests."
        )
    return BASE_URL.rstrip("/") + "/" + resolved.lstrip("/")


def send_request(case):
    req = case["request"]
    ep = case.get("endpoint") or {}
    if not ep and SUITE.get("endpoints"):
        ep = SUITE["endpoints"][0]
    if not ep:
        ep = SUITE.get("endpoint") or {}
    method = req.get("method", ep.get("method", "GET")).lower()
    path = req.get("path", ep.get("path", "/"))
    headers = replace_placeholders(req.get("headers", {}))
    query_params = replace_placeholders(req.get("query_params", {}))
    path_params = replace_placeholders(req.get("path_params", {}))
    body = replace_placeholders(req.get("body"))
    template_path = ep.get("path", path)

    url = build_url(path, path_params, template_path)
    kwargs = {
        "headers": headers,
        "params": query_params,
        "timeout": 30,
    }
    if body is not None:
        kwargs["json"] = body

    return requests.request(method, url, **kwargs)


def _case_needs_access_token(case):
    blob = json.dumps(case.get("request", {}))
    return "VALID_TOKEN" in blob


@pytest.mark.parametrize("case", SUITE["test_cases"], ids=lambda c: c["id"])
def test_api_case(case):
    missing = _unresolved_user_inputs(case)
    if missing:
        env_keys = ", ".join(__SKIP_ENV_KEYS__)
        pytest.skip(
            "Provide user values in .env (" + env_keys + ") before running "
            + case["id"] + ". Fields: " + ", ".join(missing)
        )
    if _case_needs_access_token(case) and not ACCESS_TOKEN.strip():
        pytest.skip(
            "Set ACCESS_TOKEN in .env to run " + case["id"]
            + " (uses VALID_TOKEN). Other tests can run without it."
        )
    response = send_request(case)
    expected = case["expected"]["status_code"]
    assert response.status_code == expected, (
        "Contract mismatch. Expected " + str(expected)
        + ", got " + str(response.status_code) + ". Response: " + response.text
    )
    __ASSERTION_BLOCK__
"""


def _merge_norm_for_env(norm_endpt_or_map):
    """Merge servers/security from a norm_map or pass through a single norm."""
    if not norm_endpt_or_map:
        return {}
    if "method" in norm_endpt_or_map and "path" in norm_endpt_or_map:
        return norm_endpt_or_map

    merged = {"servers": [], "security": [], "info": {}}
    seen_sec = set()
    for norm in norm_endpt_or_map.values():
        if not merged["servers"] and norm.get("servers"):
            merged["servers"] = norm["servers"]
        if not merged["info"] and norm.get("info"):
            merged["info"] = norm["info"]
        for sec in norm.get("security") or []:
            sig = json.dumps(sec, sort_keys=True, default=str)
            if sig not in seen_sec:
                merged["security"].append(sec)
                seen_sec.add(sig)
    return merged


def _auth_tokens_in_suite(test_suite):
    blob = json.dumps(test_suite or {})
    return {
        "INVALID_TOKEN": "INVALID_TOKEN" in blob,
        "EXPIRED_TOKEN": "EXPIRED_TOKEN" in blob,
    }


def CollectEnvVars(norm_endpt_or_map, test_suite=None, user_values=None):
    """Build env var placeholders from security and USER_INPUT fields."""
    norm_endpt = _merge_norm_for_env(norm_endpt_or_map)
    env = {}

    servers = norm_endpt.get("servers", [])
    if servers and isinstance(servers[0], dict):
        env["API_BASE_URL"] = servers[0].get("url", "")

    for sec in norm_endpt.get("security", []):
        if not isinstance(sec, dict):
            continue

        scheme_type = (sec.get("type") or "").lower()

        if scheme_type == "http":
            http_scheme = (sec.get("scheme") or "").lower()
            if http_scheme == "bearer":
                env["ACCESS_TOKEN"] = "<token>"
            elif http_scheme == "basic":
                env["USERNAME"] = "<username>"
                env["PASSWORD"] = "<password>"

        elif scheme_type == "oauth2":
            env["ACCESS_TOKEN"] = "<token>"

        elif scheme_type == "apikey":
            param_name = sec.get("parameterName") or sec.get("name") or "API_KEY"
            key_name = str(param_name).upper().replace("-", "_")
            env[key_name] = "<api_key>"

    if test_suite:
        auth_used = _auth_tokens_in_suite(test_suite)
        if auth_used.get("INVALID_TOKEN"):
            env["INVALID_TOKEN"] = "invalid_token_for_testing"
        if auth_used.get("EXPIRED_TOKEN"):
            env["EXPIRED_TOKEN"] = "expired_token_for_testing"

        fields = extract_user_input_fields(test_suite)
        user_values = user_values or {}
        for name in fields:
            env[field_to_env_key(name)] = user_values.get(name, "")

    return env


def BuildEnvFile(norm_endpt_or_map, base_url_override=None, test_suite=None, user_values=None):
    env = CollectEnvVars(norm_endpt_or_map, test_suite, user_values)
    if base_url_override:
        env["API_BASE_URL"] = base_url_override

    lines = [f"{k}={v}" for k, v in env.items()]

    if test_suite:
        fields = extract_user_input_fields(test_suite)
        if fields:
            lines.append("")
            lines.append("# Values required for tests marked requires_user_input")
            for extra in build_user_input_env_lines(fields, user_values):
                key = extra.split("=", 1)[0].split("#", 1)[0].strip()
                if key not in env:
                    lines.append(extra)

    return "\n".join(lines) + "\n"


def _merge_user_input_fields(test_suite, user_input_defaults=None):
    """Field names from placeholders, user_inputs metadata, and UI defaults."""
    fields = dict(extract_user_input_fields(test_suite))
    for name in (user_input_defaults or {}):
        if name and name not in fields:
            fields[name] = ""
    return fields


def _build_auth_env_block(norm_endpt_or_map=None, test_suite=None):
    """Python source for auth-related os.getenv lines in generated pytest."""
    lines = [
        'ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")',
        'API_KEY = os.getenv("API_KEY", "")',
        'USERNAME = os.getenv("USERNAME", "")',
        'PASSWORD = os.getenv("PASSWORD", "")',
        'INVALID_TOKEN = os.getenv("INVALID_TOKEN", "invalid_token_for_testing")',
        'EXPIRED_TOKEN = os.getenv("EXPIRED_TOKEN", "expired_token_for_testing")',
    ]
    seen = {
        "ACCESS_TOKEN", "API_KEY", "USERNAME", "PASSWORD",
        "INVALID_TOKEN", "EXPIRED_TOKEN", "API_BASE_URL",
    }
    if norm_endpt_or_map:
        for key, default in CollectEnvVars(norm_endpt_or_map, test_suite).items():
            if key in seen or key.startswith("USER_INPUT_"):
                continue
            lines.append(
                f'{key} = os.getenv({json.dumps(key)}, {json.dumps(str(default))})'
            )
            seen.add(key)
    return "\n".join(lines)


def _build_user_input_block(fields, user_input_defaults=None):
    """Python source for USER_INPUT_VALUES dict in generated pytest."""
    if not fields:
        return "USER_INPUT_VALUES = {}\n"

    user_input_defaults = user_input_defaults or {}
    lines = ["USER_INPUT_VALUES = {"]
    for name in sorted(fields):
        env_key = field_to_env_key(name)
        default = user_input_defaults.get(name, "")
        default_json = json.dumps(str(default))
        lines.append(
            f'    {json.dumps(name)}: os.getenv({json.dumps(env_key)}, {default_json}).strip(),'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _embed_suite_b64(test_suite_json):
    payload = json.dumps(test_suite_json, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(payload).decode("ascii")


def BuildPytestFile(test_suite_json, user_input_defaults=None, norm_endpt_or_map=None):
    """
    Generate a pytest module.

    test_suite_json should be the raw LLM output (with USER_INPUT: placeholders).
    user_input_defaults: optional values from the Streamlit UI baked in as getenv defaults.
    norm_endpt_or_map: optional norm map for endpoint-specific auth env vars.
    """
    fields = _merge_user_input_fields(test_suite_json, user_input_defaults)
    auth_block = _build_auth_env_block(norm_endpt_or_map, test_suite_json)
    user_input_block = _build_user_input_block(fields, user_input_defaults)
    suite_b64 = _embed_suite_b64(test_suite_json)

    if fields:
        skip_env_keys = ", ".join(json.dumps(field_to_env_key(n)) for n in sorted(fields))
    else:
        skip_env_keys = '""'

    code = _PYTEST_TEMPLATE
    code = code.replace("__SUITE_B64__", json.dumps(suite_b64))
    code = code.replace("__AUTH_ENV_BLOCK__", auth_block)
    code = code.replace("__USER_INPUT_BLOCK__", user_input_block.rstrip())
    code = code.replace("__SKIP_ENV_KEYS__", skip_env_keys)
    code = code.replace("__ASSERTION_BLOCK__", "    _check_assertions(case, response)")
    return textwrap.dedent(code)
