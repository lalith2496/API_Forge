import json
import re
import uuid as uuid_lib

from user_inputs import (
    USER_INPUT_PATTERN,
    extract_user_input_fields,
    field_to_env_key,
    replace_user_inputs,
)
import postman_scripts

_BRACE_PARAM = re.compile(r"{([^}]+)}")
# Match longest-first so VALID_TOKEN does not match inside INVALID_TOKEN / {{INVALID_TOKEN}}
_AUTH_PLACEHOLDER_PATTERN = re.compile(
    r"EXPIRED_TOKEN|INVALID_TOKEN|VALID_TOKEN"
)

def _primary_token_var(security):
    """Map VALID_TOKEN to the collection variable for this endpoint's auth scheme."""
    for sec in security or []:
        if not isinstance(sec, dict):
            continue
        sec_type = (sec.get("type") or "").lower()
        sec_scheme = (sec.get("scheme") or "").lower()
        if sec_type == "http" and sec_scheme == "bearer":
            return "ACCESS_TOKEN"
        if sec_type == "oauth2":
            return "ACCESS_TOKEN"
        if sec_type == "apikey":
            param = sec.get("parameterName") or sec.get("name") or "API_KEY"
            return str(param).upper().replace("-", "_")
    return "ACCESS_TOKEN"


def _replace_auth_placeholders(value, primary_token_var):
    """Convert VALID_TOKEN / INVALID_TOKEN / EXPIRED_TOKEN to {{var}} syntax."""
    if not isinstance(value, str):
        return value

    def _repl(match):
        token = match.group(0)
        if token == "VALID_TOKEN":
            return "{{" + primary_token_var + "}}"
        return "{{" + token + "}}"

    return _AUTH_PLACEHOLDER_PATTERN.sub(_repl, value)


def _scan_auth_placeholders(test_suite):
    """Which auth placeholder collection variables are referenced in the suite."""
    blob = json.dumps(test_suite or {})
    return {
        "INVALID_TOKEN": "INVALID_TOKEN" in blob,
        "EXPIRED_TOKEN": "EXPIRED_TOKEN" in blob,
    }


def _to_postman_vars(value, primary_token_var="ACCESS_TOKEN", user_values=None):
    """
    Convert LLM placeholders to Postman {{variable}} syntax:
    USER_INPUT:<field>, VALID_TOKEN, INVALID_TOKEN, EXPIRED_TOKEN.
    """
    if isinstance(value, str):
        s = replace_user_inputs(value, user_values or {})
        s = USER_INPUT_PATTERN.sub(
            lambda m: "{{" + field_to_env_key(m.group(1)) + "}}", s
        )
        return _replace_auth_placeholders(s, primary_token_var)
    if isinstance(value, list):
        return [_to_postman_vars(v, primary_token_var, user_values) for v in value]
    if isinstance(value, dict):
        return {
            k: _to_postman_vars(v, primary_token_var, user_values) for k, v in value.items()
        }
    return value


def _derive_path_values(template_path, resolved_path):
    """Align /pet/{petId} with /pet/123 -> {'petId': '123'}."""
    out = {}
    if not template_path or not resolved_path:
        return out
    t_segs = template_path.strip("/").split("/")
    r_segs = resolved_path.strip("/").split("/")
    if len(t_segs) != len(r_segs):
        return out
    for t_seg, r_seg in zip(t_segs, r_segs):
        m = _BRACE_PARAM.fullmatch(t_seg)
        if m:
            out[m.group(1)] = r_seg
    return out


def _build_url_object(base_url_var, case_path, template_path, path_params, query_params):
    """
    Build a Postman url object with proper :param segments and path variables.
    Uses the templated endpoint path for structure and fills variable values
    from path_params or by aligning a resolved case path.
    """
    # Prefer the spec template path for structure: it has clean {param} braces,
    # whereas the case path may be resolved or contain {{USER_INPUT_*}} vars.
    if template_path and "{" in template_path:
        structural = template_path
    elif case_path and "{" in case_path:
        structural = case_path
    else:
        structural = case_path or template_path or "/"

    param_names = _BRACE_PARAM.findall(structural)

    values = {k: v for k, v in (path_params or {}).items()}
    # Align template /pets/{id} with resolved /pets/1 or /pets/{{USER_INPUT_*}}
    if case_path and template_path and "{" in template_path:
        for k, v in _derive_path_values(template_path, case_path).items():
            values.setdefault(k, v)

    postman_path = structural
    for name in param_names:
        postman_path = postman_path.replace("{" + name + "}", ":" + name)

    if not postman_path.startswith("/"):
        postman_path = "/" + postman_path

    raw = base_url_var + postman_path
    if query_params:
        raw += "?" + "&".join(f"{k}={v}" for k, v in query_params.items())

    segments = [s for s in postman_path.split("/") if s]

    query_list = [
        {"key": k, "value": str(v)}
        for k, v in (query_params or {}).items()
    ]

    path_variable_list = [
        {"key": name, "value": str(values.get(name, ""))}
        for name in param_names
    ]

    url_obj = {
        "raw": raw,
        "host": [base_url_var],
        "path": segments,
    }

    if query_list:
        url_obj["query"] = query_list
    if path_variable_list:
        url_obj["variable"] = path_variable_list

    return url_obj


def _build_auth_object(security):
    """
    Build a Postman auth object from the normalized security list.
    Returns None if no supported scheme is present.
    """
    for sec in (security or []):
        sec_type = (sec.get("type") or "").lower()
        sec_scheme = (sec.get("scheme") or "").lower()

        if sec_type == "http" and sec_scheme == "bearer":
            return {
                "type": "bearer",
                "bearer": [
                    {"key": "token", "value": "{{ACCESS_TOKEN}}", "type": "string"}
                ],
            }
        elif sec_type == "http" and sec_scheme == "basic":
            return {
                "type": "basic",
                "basic": [
                    {"key": "username", "value": "{{USERNAME}}", "type": "string"},
                    {"key": "password", "value": "{{PASSWORD}}", "type": "string"},
                ],
            }
        elif sec_type == "apikey":
            param_name = sec.get("parameterName") or sec.get("name") or "X-API-KEY"
            var_name = _primary_token_var([sec])
            return {
                "type": "apikey",
                "apikey": [
                    {"key": "key", "value": str(param_name), "type": "string"},
                    {"key": "value", "value": "{{" + var_name + "}}", "type": "string"},
                    {"key": "in", "value": sec.get("in") or "header", "type": "string"},
                ],
            }
        elif sec_type == "oauth2":
            return {
                "type": "oauth2",
                "oauth2": [
                    {"key": "accessToken", "value": "{{ACCESS_TOKEN}}", "type": "string"},
                    {"key": "tokenType", "value": "bearer", "type": "string"},
                ],
            }

    return None


def _request_var_refs(req, url_obj, header_list, body_obj, auth_obj):
    """Collect {{VAR}} names used in a Postman request item."""
    blobs = [
        json.dumps(url_obj),
        json.dumps(header_list),
        json.dumps(req),
    ]
    if body_obj:
        blobs.append(json.dumps(body_obj))
    if auth_obj:
        blobs.append(json.dumps(auth_obj))
    return postman_scripts.extract_postman_var_refs(*blobs)


def _case_norm(case, norm_endpt):
    """Use normalized endpoint or fall back to case endpoint metadata."""
    if norm_endpt:
        return norm_endpt
    ep = case.get("endpoint") or {}
    req = case.get("request") or {}
    return {
        "method": ep.get("method") or req.get("method", "GET"),
        "path": ep.get("path") or req.get("path", "/"),
        "security": [],
    }


def _case_to_item(case, norm_endpt, base_url_var, user_values=None):
    """Convert one LLM test case into a Postman item object."""
    norm_endpt = _case_norm(case, norm_endpt)
    primary_token = _primary_token_var(norm_endpt.get("security", []))
    req = _to_postman_vars(case.get("request", {}), primary_token, user_values)
    method = req.get("method", norm_endpt.get("method", "GET")).upper()
    case_path = req.get("path", norm_endpt.get("path", "/"))
    template_path = norm_endpt.get("path", case_path)
    headers_dict = req.get("headers") or {}
    query_params = req.get("query_params") or {}
    path_params = req.get("path_params") or {}
    body = req.get("body")

    header_list = [
        {"key": k, "value": str(v) if v is not None else ""}
        for k, v in headers_dict.items()
    ]

    has_auth_header = any(h["key"].lower() == "authorization" for h in header_list)
    has_content_type = any(h["key"].lower() == "content-type" for h in header_list)

    if body is not None and not has_content_type:
        header_list.append({"key": "Content-Type", "value": "application/json"})

    auth_obj = None
    if not has_auth_header:
        auth_obj = _build_auth_object(norm_endpt.get("security", []))

    body_obj = None
    if body is not None:
        body_obj = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }

    url_obj = _build_url_object(
        base_url_var, case_path, template_path, path_params, query_params
    )

    var_refs = _request_var_refs(req, url_obj, header_list, body_obj, auth_obj)
    required_vars = postman_scripts.required_vars_for_request(var_refs)
    # Only block on ACCESS_TOKEN when this case actually sends a valid token
    req_blob = json.dumps(case.get("request", {}))
    if "ACCESS_TOKEN" in required_vars and "VALID_TOKEN" not in req_blob:
        if "{{ACCESS_TOKEN}}" not in json.dumps(header_list):
            if not auth_obj or "{{ACCESS_TOKEN}}" not in json.dumps(auth_obj):
                required_vars = [v for v in required_vars if v != "ACCESS_TOKEN"]

    item = {
        "name": f"{case.get('id', '?')} - {case.get('description', '')}",
        "event": postman_scripts.request_events(case, required_vars),
        "request": {
            "method": method,
            "header": header_list,
            "url": url_obj,
        },
        "response": [],
    }
    if auth_obj:
        item["request"]["auth"] = auth_obj

    if body_obj:
        item["request"]["body"] = body_obj

    notes = case.get("notes", "")
    if notes:
        item["request"]["description"] = notes

    return item


def _case_ep(case, test_suite=None):
    """Resolve {method, path} from case.endpoint, request, or suite metadata."""
    ep = case.get("endpoint")
    if isinstance(ep, dict) and ep.get("path"):
        return {
            "method": str(ep.get("method", "GET")).upper(),
            "path": str(ep["path"]),
        }
    req = case.get("request") or {}
    if req.get("path"):
        return {
            "method": str(req.get("method", "GET")).upper(),
            "path": str(req["path"]),
        }
    suite = test_suite or {}
    for src in (suite.get("endpoints") or [], [suite.get("endpoint")] if suite.get("endpoint") else []):
        for item in src:
            if isinstance(item, dict) and item.get("path"):
                return {
                    "method": str(item.get("method", "GET")).upper(),
                    "path": str(item["path"]),
                }
    return {"method": "GET", "path": "/"}


def _lookup_norm(norm_map, ep_dict):
    """Find full norm for a case endpoint {method, path}."""
    if isinstance(norm_map, dict) and norm_map.get("method"):
        return norm_map
    method = str(ep_dict.get("method", "")).upper()
    path = str(ep_dict.get("path", ""))
    for norm in (norm_map or {}).values():
        if not isinstance(norm, dict):
            continue
        if norm.get("method", "").upper() == method and norm.get("path") == path:
            return norm
    return None


def _is_norm_map(norm_endpt_or_map):
    if not isinstance(norm_endpt_or_map, dict):
        return False
    if norm_endpt_or_map.get("method"):
        return False
    return any(isinstance(v, dict) and v.get("path") for v in norm_endpt_or_map.values())


def _build_items(test_cases, norms, norm_map, base_url_var, test_suite, user_values=None):
    items = []
    for case in test_cases:
        ep = _case_ep(case, test_suite)
        norm = _lookup_norm(norm_map, ep) if norm_map else None
        if not norm and isinstance(norms, dict):
            norm = next(iter(norms.values()), None)
        try:
            items.append(_case_to_item(case, norm, base_url_var, user_values))
        except Exception as e:
            items.append({
                "name": f"{case.get('id', '?')} - EXPORT ERROR",
                "request": {"method": "GET", "header": [], "url": {"raw": ""}},
                "response": [],
                "_error": str(e),
            })
    return items


def _collect_variables(norm_endpt_or_map, test_suite=None, user_values=None):
    """
    Derive collection-level variables from endpoint(s).
    Merges auth vars across a norm_map.
    """
    if isinstance(norm_endpt_or_map, dict) and norm_endpt_or_map.get("method"):
        norms = [norm_endpt_or_map]
    else:
        norms = list((norm_endpt_or_map or {}).values())

    base_url = ""
    for norm in norms:
        servers = norm.get("servers", [])
        if servers and isinstance(servers[0], dict):
            base_url = servers[0].get("url", "")
            break

    variables = [
        {"key": "BASE_URL", "value": base_url, "type": "default"},
    ]

    seen = set()

    for norm in norms:
        for sec in norm.get("security", []):
            sec_type = (sec.get("type") or "").lower()
            sec_scheme = (sec.get("scheme") or "").lower()

            if sec_type == "http" and sec_scheme == "bearer" and "ACCESS_TOKEN" not in seen:
                variables.append({"key": "ACCESS_TOKEN", "value": "", "type": "secret"})
                seen.add("ACCESS_TOKEN")

            elif sec_type == "http" and sec_scheme == "basic":
                if "USERNAME" not in seen:
                    variables.append({"key": "USERNAME", "value": "", "type": "default"})
                    variables.append({"key": "PASSWORD", "value": "", "type": "secret"})
                    seen.update({"USERNAME", "PASSWORD"})

            elif sec_type == "apikey":
                param_name = sec.get("parameterName") or sec.get("name") or "X-API-Key"
                env_key = str(param_name).upper().replace("-", "_")
                if env_key not in seen:
                    variables.append({"key": env_key, "value": "", "type": "secret"})
                    seen.add(env_key)

            elif sec_type == "oauth2" and "ACCESS_TOKEN" not in seen:
                variables.append({"key": "ACCESS_TOKEN", "value": "", "type": "secret"})
                seen.add("ACCESS_TOKEN")

    if test_suite:
        auth_used = _scan_auth_placeholders(test_suite)
        if auth_used.get("INVALID_TOKEN") and "INVALID_TOKEN" not in seen:
            variables.append({
                "key": "INVALID_TOKEN",
                "value": "invalid_token_for_testing",
                "type": "secret",
            })
            seen.add("INVALID_TOKEN")
        if auth_used.get("EXPIRED_TOKEN") and "EXPIRED_TOKEN" not in seen:
            variables.append({
                "key": "EXPIRED_TOKEN",
                "value": "expired_token_for_testing",
                "type": "secret",
            })
            seen.add("EXPIRED_TOKEN")

        user_values = user_values or {}
        for name in extract_user_input_fields(test_suite):
            if user_values.get(name):
                continue
            key = field_to_env_key(name)
            if key not in seen:
                variables.append({
                    "key": key,
                    "value": "",
                    "type": "default",
                })
                seen.add(key)

    return variables


def BuildPostmanCollection(test_suite_json, norm_endpt_or_map, user_values=None):
    """
    Convert an LLM-generated test suite into a Postman collection.
    norm_endpt_or_map: single normalized endpoint dict OR {endpoint_key: norm}.
    """
    base_url_var = "{{BASE_URL}}"
    variables = _collect_variables(norm_endpt_or_map, test_suite_json, user_values)

    test_cases = test_suite_json.get("test_cases") or []
    if not isinstance(test_cases, list):
        test_cases = []

    is_multi = _is_norm_map(norm_endpt_or_map)
    norms = norm_endpt_or_map if is_multi else {"single": norm_endpt_or_map}
    norm_map = norm_endpt_or_map if is_multi else {}

    from collections import defaultdict

    endpoint_folders = defaultdict(list)
    for case in test_cases:
        ep = _case_ep(case, test_suite_json)
        folder = f"{ep['method']} {ep['path']}"
        endpoint_folders[folder].append(case)

    declared = test_suite_json.get("endpoints") or []
    use_folders = is_multi or len(declared) > 1 or len(endpoint_folders) > 1

    if use_folders and endpoint_folders:
        items = []
        for folder_name in sorted(endpoint_folders):
            items.append({
                "name": folder_name,
                "item": _build_items(
                    endpoint_folders[folder_name], norms, norm_map, base_url_var, test_suite_json, user_values
                ),
            })
    else:
        items = _build_items(test_cases, norms, norm_map, base_url_var, test_suite_json, user_values)

    api_title = ""
    if is_multi and norms:
        api_title = next(iter(norms.values())).get("info", {}).get("title", "")
    elif not is_multi:
        api_title = norm_endpt_or_map.get("info", {}).get("title", "")

    endpoint_lines = []
    for ep in test_suite_json.get("endpoints") or []:
        endpoint_lines.append(f"  - {ep.get('method')} {ep.get('path')}")

    collection = {
        "info": {
            "_postman_id": str(uuid_lib.uuid4()),
            "name": test_suite_json.get("test_suite_name", "API Test Suite"),
            "description": (
                "Generated by API Forge.\n\n"
                "Before running: set Collection Variables (click collection → Variables).\n"
                "Pre-request scripts block each request until required vars are non-empty.\n\n"
                + (f"Endpoints:\n" + "\n".join(endpoint_lines) + "\n\n" if endpoint_lines else "")
                + f"API: {api_title}"
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "event": postman_scripts.collection_events(),
        "item": items,
        "variable": variables,
    }
    return collection
