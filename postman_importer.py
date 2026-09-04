"""Parse Postman Collection v2.1 into API Forge structures."""

from __future__ import annotations

import json
import re
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlparse

import ingester

_BRACE = re.compile(r"\{([^}]+)\}")
_COLON_PARAM = re.compile(r":([^/]+)")


def _walk_items(items: list, folder: str = "") -> Iterator[dict]:
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("item"):
            name = item.get("name") or folder
            yield from _walk_items(item["item"], name)
        elif item.get("request"):
            yield item


def _resolve_postman_var(value: str, variables: dict[str, str]) -> str:
    if not isinstance(value, str):
        return str(value)
    out = value
    for key, val in variables.items():
        out = out.replace("{{" + key + "}}", val)
        out = out.replace("{{" + key.lower() + "}}", val)
    return out


def _collection_variables(collection: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for var in collection.get("variable") or []:
        if isinstance(var, dict) and var.get("key"):
            out[str(var["key"])] = str(var.get("value") or "")
    return out


def _url_parts(url_obj: Any, variables: dict[str, str]) -> tuple[str, str, dict, dict]:
    """Return base_url, path_template, query_params, path_param_values."""
    if isinstance(url_obj, str):
        raw = _resolve_postman_var(url_obj, variables)
        parsed = urlparse(raw)
        base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else parsed.netloc
        path = parsed.path or "/"
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        return base.rstrip("/"), path, query, {}

    if not isinstance(url_obj, dict):
        return "", "/", {}, {}

    raw = _resolve_postman_var(str(url_obj.get("raw") or ""), variables)
    if raw.startswith("http"):
        parsed = urlparse(raw)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
    else:
        host = url_obj.get("host") or []
        if isinstance(host, list):
            host_str = ".".join(str(h) for h in host if h)
        else:
            host_str = str(host)
        host_str = _resolve_postman_var(host_str, variables)
        protocol = _resolve_postman_var(str(url_obj.get("protocol") or "https"), variables)
        base = f"{protocol}://{host_str}" if host_str else ""
        segments = url_obj.get("path") or []
        path = "/" + "/".join(str(s) for s in segments if s is not None)

    path = _resolve_postman_var(path, variables)
    path_template = path
    for m in _COLON_PARAM.finditer(path):
        path_template = path_template.replace(":" + m.group(1), "{" + m.group(1) + "}")

    query: dict[str, str] = {}
    for q in url_obj.get("query") or []:
        if isinstance(q, dict) and q.get("key"):
            query[str(q["key"])] = _resolve_postman_var(str(q.get("value") or ""), variables)

    path_values: dict[str, str] = {}
    for pv in url_obj.get("variable") or []:
        if isinstance(pv, dict) and pv.get("key"):
            path_values[str(pv["key"])] = _resolve_postman_var(str(pv.get("value") or ""), variables)

    if not query and raw and "?" in raw:
        query = dict(parse_qsl(urlparse(raw).query, keep_blank_values=True))

    return base.rstrip("/"), path_template, query, path_values


def _parse_body(body_obj: Any) -> tuple[Any, str | None]:
    if not body_obj or not isinstance(body_obj, dict):
        return None, None
    mode = body_obj.get("mode") or "raw"
    if mode == "raw":
        raw = body_obj.get("raw") or ""
        if raw.strip().startswith("{") or raw.strip().startswith("["):
            try:
                return json.loads(raw), body_obj.get("options", {}).get("raw", {}).get("language") or "application/json"
            except json.JSONDecodeError:
                pass
        return raw, "text/plain"
    if mode == "urlencoded":
        data = {}
        for row in body_obj.get("urlencoded") or []:
            if isinstance(row, dict) and row.get("key"):
                data[str(row["key"])] = str(row.get("value") or "")
        return data, "application/x-www-form-urlencoded"
    if mode == "formdata":
        data = {}
        for row in body_obj.get("formdata") or []:
            if isinstance(row, dict) and row.get("key"):
                data[str(row["key"])] = str(row.get("value") or "")
        return data, "multipart/form-data"
    return None, None


def _headers_dict(header_list: list) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in header_list or []:
        if isinstance(h, dict) and h.get("key") and not h.get("disabled"):
            out[str(h["key"])] = str(h.get("value") or "")
    return out


def _security_from_auth(auth: Any) -> list[dict]:
    if not auth or not isinstance(auth, dict):
        return []
    auth_type = (auth.get("type") or "").lower()
    if auth_type == "bearer":
        return [{"type": "http", "scheme": "bearer"}]
    if auth_type == "apikey":
        for row in auth.get("apikey") or []:
            if isinstance(row, dict) and row.get("key") == "key":
                return [{
                    "type": "apiKey",
                    "in": "header",
                    "parameterName": str(row.get("value") or "X-API-Key"),
                }]
    return []


def _build_norm(
    method: str,
    path: str,
    base_url: str,
    headers: dict,
    query: dict,
    path_values: dict,
    body: Any,
    content_type: str | None,
    security: list,
) -> dict:
    parameters = []
    for name in _BRACE.findall(path):
        parameters.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        })
    for name in query:
        parameters.append({
            "name": name,
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
            "example": query[name],
        })
    for name, value in path_values.items():
        parameters.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
            "example": value,
        })

    request_body = None
    if body is not None and method in {"POST", "PUT", "PATCH", "DELETE"}:
        ct = content_type or headers.get("Content-Type") or "application/json"
        if ct == "json":
            ct = "application/json"
        media: dict[str, Any] = {}
        if isinstance(body, dict):
            media[ct] = {
                "schema": {
                    "type": "object",
                    "properties": {k: {"type": "string"} for k in body},
                },
                "example": body,
            }
        else:
            media[ct] = {"schema": {"type": "string"}, "example": body}
        request_body = {"required": True, "content": media}

    return {
        "method": method,
        "path": path,
        "servers": [{"url": base_url}] if base_url else [],
        "summary": f"{method} {path}",
        "parameters": parameters,
        "requestBody": request_body,
        "responses": {"200": {"description": "OK", "content": {}}},
        "security": security,
    }


def _item_to_endpoint(item: dict, variables: dict[str, str], index: int) -> tuple[dict, dict, dict] | None:
    req = item.get("request") or {}
    method = str(req.get("method") or "GET").upper()
    base_url, path, query, path_values = _url_parts(req.get("url"), variables)
    headers = _headers_dict(req.get("header"))
    body, body_ct = _parse_body(req.get("body"))
    security = _security_from_auth(req.get("auth"))

    if not path:
        return None

    endpoint = {
        "method": method,
        "path": path,
        "summary": item.get("name") or f"{method} {path}",
        "operationId": f"postman_{index}",
        "responses": ["200"],
    }
    norm = _build_norm(method, path, base_url, headers, query, path_values, body, body_ct, security)
    imported_case = {
        "id": f"TC-{index:02d}",
        "endpoint": {"method": method, "path": path},
        "category": "happy_path",
        "description": item.get("name") or f"Imported Postman — {method} {path}",
        "requires_user_input": False,
        "request": {
            "method": method,
            "path": path,
            "headers": headers,
            "query_params": query,
            "path_params": path_values,
            "body": body,
        },
        "expected": {"status_code": 200, "response_assertions": []},
        "notes": "Imported Postman request",
    }
    return endpoint, norm, imported_case


def parse_collection(data: dict) -> dict:
    """
    Parse Postman Collection v2.1.

    Returns bundle: spec, endpoints, norm_map, source, imported_cases, base_url, error?
    """
    if not isinstance(data, dict):
        return {"error": "Postman collection must be a JSON object"}

    info = data.get("info") or {}
    if not data.get("item"):
        return {"error": "Not a valid Postman collection — missing item array"}

    variables = _collection_variables(data)
    endpoints: list[dict] = []
    norm_map: dict[str, dict] = {}
    imported_cases: list[dict] = []
    servers: set[str] = set()

    idx = 0
    for item in _walk_items(data.get("item") or []):
        idx += 1
        parsed = _item_to_endpoint(item, variables, idx)
        if not parsed:
            continue
        endpoint, norm, case = parsed
        key = ingester.endpoint_key(endpoint)
        if key in norm_map:
            continue
        endpoints.append(endpoint)
        norm_map[key] = norm
        imported_cases.append(case)
        for srv in norm.get("servers") or []:
            url = srv.get("url")
            if url:
                servers.add(str(url).rstrip("/"))

    if not endpoints:
        return {"error": "No requests found in Postman collection"}

    base_url = next(iter(servers), "")
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": info.get("name") or "Imported Postman Collection",
            "version": info.get("version") or "1.0.0",
        },
        "servers": [{"url": base_url}] if base_url else [],
        "_source": "postman",
    }

    return {
        "spec": spec,
        "endpoints": endpoints,
        "norm_map": norm_map,
        "source": "postman",
        "imported_cases": imported_cases,
        "base_url": base_url,
    }
