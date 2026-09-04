"""Parse cURL commands into API Forge endpoint + norm_map structures."""

from __future__ import annotations

import json
import re
import shlex
from typing import Any
from urllib.parse import parse_qsl, urlparse

import ingester

_CURL_FLAGS_WITH_VALUE = frozenset({
    "-X", "--request",
    "-H", "--header",
    "-d", "--data", "--data-raw", "--data-binary", "--data-urlencode",
    "-u", "--user",
    "-b", "--cookie",
})


def _normalize_command(command: str) -> str:
    text = command.strip()
    if not text:
        return ""
    text = re.sub(r"\\\s*\n", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _parse_headers(tokens: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-H", "--header") and i + 1 < len(tokens):
            part = tokens[i + 1]
            if ":" in part:
                name, val = part.split(":", 1)
                headers[name.strip()] = val.strip()
            i += 2
            continue
        i += 1
    return headers


def _parse_data(tokens: list[str]) -> tuple[Any, str | None]:
    for flag in ("--data-raw", "--data-binary", "--data-urlencode", "--data", "-d"):
        if flag in tokens:
            idx = tokens.index(flag)
            if idx + 1 >= len(tokens):
                continue
            raw = tokens[idx + 1]
            ct = None
            if raw.startswith("{") or raw.startswith("["):
                try:
                    return json.loads(raw), "application/json"
                except json.JSONDecodeError:
                    pass
            return raw, "application/x-www-form-urlencoded"
    return None, None


def _parse_method(tokens: list[str], headers: dict[str, str]) -> str:
    for flag in ("-X", "--request"):
        if flag in tokens:
            idx = tokens.index(flag)
            if idx + 1 < len(tokens):
                return tokens[idx + 1].upper()
    return "POST" if any(t in tokens for t in ("-d", "--data", "--data-raw")) else "GET"


def _find_url(tokens: list[str]) -> str:
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if tok in _CURL_FLAGS_WITH_VALUE:
            skip_next = True
            continue
        if tok.startswith("-"):
            continue
        if tok.lower() == "curl":
            continue
        if tok.startswith("http://") or tok.startswith("https://"):
            return tok.strip("'\"")
    return ""


def _path_template(path: str) -> str:
    segments = [s for s in path.split("/") if s]
    out = []
    for seg in segments:
        if seg.isdigit():
            out.append("{id}")
        else:
            out.append(seg)
    return "/" + "/".join(out) if out else "/"


def _build_norm(
    method: str,
    path: str,
    base_url: str,
    headers: dict,
    query: dict,
    body: Any,
    content_type: str | None,
) -> dict:
    query_params = []
    path_params = []
    for name, value in query.items():
        query_params.append({
            "name": name,
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
            "example": value,
        })
    for seg in path.split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            path_params.append({
                "name": seg[1:-1],
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            })

    request_body = None
    if body is not None and method in {"POST", "PUT", "PATCH", "DELETE"}:
        ct = content_type or headers.get("Content-Type") or "application/json"
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

    security = []
    auth = headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        security.append({"type": "http", "scheme": "bearer"})
    elif auth:
        security.append({"type": "apiKey", "in": "header", "parameterName": "Authorization"})

    return {
        "method": method,
        "path": path,
        "servers": [{"url": base_url.rstrip("/")}],
        "summary": f"{method} {path}",
        "parameters": query_params + path_params,
        "requestBody": request_body,
        "responses": {"200": {"description": "OK", "content": {}}},
        "security": security,
    }


def parse_curl(command: str) -> dict:
    """
    Parse a cURL command.

    Returns bundle:
      spec, endpoints, norm_map, source, error?
    """
    text = _normalize_command(command)
    if not text:
        return {"error": "Empty cURL command"}
    if not text.lower().lstrip().startswith("curl"):
        return {"error": "Input does not start with curl"}

    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        return {"error": f"Could not parse cURL: {exc}"}

    url = _find_url(tokens)
    if not url:
        return {"error": "No URL found in cURL command"}

    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"
    path = _path_template(path)

    headers = _parse_headers(tokens)
    body, data_ct = _parse_data(tokens)
    method = _parse_method(tokens, headers)

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    norm = _build_norm(method, path, base_url, headers, query, body, data_ct or headers.get("Content-Type"))

    endpoint = {
        "method": method,
        "path": path,
        "summary": f"Imported cURL — {method} {path}",
        "operationId": "curl_import",
        "responses": ["200"],
    }
    key = ingester.endpoint_key(endpoint)
    norm_map = {key: norm}

    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Imported cURL request", "version": "1.0.0"},
        "servers": [{"url": base_url}],
        "_source": "curl",
    }

    imported_case = {
        "id": "TC-01",
        "endpoint": {"method": method, "path": path},
        "category": "happy_path",
        "description": "Imported from cURL",
        "requires_user_input": False,
        "request": {
            "method": method,
            "path": path,
            "headers": headers,
            "query_params": query,
            "path_params": {},
            "body": body,
        },
        "expected": {"status_code": 200, "response_assertions": []},
        "notes": "Imported cURL",
    }

    return {
        "spec": spec,
        "endpoints": [endpoint],
        "norm_map": norm_map,
        "source": "curl",
        "imported_cases": [imported_case],
        "base_url": base_url,
    }
