"""Canonical request templates preserving full OpenAPI JSON schema shape."""

from __future__ import annotations

import copy
from typing import Any, Optional


def _pick_content_type(content: dict) -> tuple[str, dict]:
    if not content:
        return "application/json", {}
    preferred = (
        "application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
        "text/plain",
    )
    for ct in preferred:
        if ct in content:
            return ct, content[ct]
    ct, media = next(iter(content.items()))
    return str(ct), media if isinstance(media, dict) else {}


def _scalar_example(schema: dict, depth: int = 0) -> Any:
    if not schema or not isinstance(schema, dict) or depth > 8:
        return {}
    if schema.get("enum"):
        return schema["enum"][0]
    schema_type = schema.get("type")
    if schema_type == "integer":
        return int(schema.get("minimum") or 1)
    if schema_type == "number":
        return float(schema.get("minimum") or 1.0)
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        fmt = schema.get("format")
        if fmt == "date-time":
            return "2024-01-01T00:00:00Z"
        if fmt == "date":
            return "2024-01-01"
        if fmt == "email":
            return "user@example.com"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000001"
        return "string"
    if schema.get("allOf"):
        merged: dict = {}
        for part in schema["allOf"]:
            val = _full_example_from_schema(part, depth + 1)
            if isinstance(val, dict):
                merged.update(val)
        return merged
    return {}


def _walk_schema_fields(
    schema: dict,
    prefix: str = "",
    depth: int = 0,
) -> list[dict]:
    """Collect field metadata for body/query/path mutation."""
    if not schema or not isinstance(schema, dict) or depth > 8:
        return []

    fields: list[dict] = []
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])

    for name, prop in props.items():
        path = f"{prefix}.{name}" if prefix else name
        field_type = prop.get("type") or ("object" if prop.get("properties") else "string")
        fields.append({
            "path": path,
            "name": name,
            "type": field_type,
            "format": prop.get("format"),
            "enum": prop.get("enum"),
            "required": name in required,
            "minLength": prop.get("minLength"),
            "maxLength": prop.get("maxLength"),
            "minimum": prop.get("minimum"),
            "maximum": prop.get("maximum"),
        })
        if prop.get("properties"):
            fields.extend(_walk_schema_fields(prop, path, depth + 1))

    return fields


def _full_example_from_schema(schema: dict, depth: int = 0) -> Any:
    """Build example including ALL properties (required + optional)."""
    if not schema or not isinstance(schema, dict) or depth > 8:
        return {}

    if schema.get("enum"):
        return schema["enum"][0]

    schema_type = schema.get("type")
    if schema_type == "object" or schema.get("properties"):
        out = {}
        for name, prop in (schema.get("properties") or {}).items():
            out[name] = _full_example_from_schema(prop, depth + 1)
        return out

    if schema_type == "array":
        items = schema.get("items") or {}
        return [_full_example_from_schema(items, depth + 1)]

    return _scalar_example(schema, depth)


def build_reference_body(
    norm_endpoint: Optional[dict],
) -> tuple[Any, str, list[dict], bool]:
    """
    Return (body, content_type, field_meta, body_required).
    Uses the exact spec/collection example when present — no schema padding.
    Falls back to generated schema example only when no explicit example exists.
    """
    if not norm_endpoint:
        return None, "application/json", [], False

    rb = norm_endpoint.get("requestBody")
    if not rb or not isinstance(rb, dict):
        ref = norm_endpoint.get("_reference_body")
        if ref is not None:
            ct = norm_endpoint.get("_reference_content_type") or "application/json"
            return copy.deepcopy(ref), ct, [], True
        return None, "application/json", [], False

    content = rb.get("content") or {}
    content_type, media = _pick_content_type(content)
    body_required = bool(rb.get("required"))
    schema = media.get("schema") or {}
    field_meta = _walk_schema_fields(schema)

    if media.get("example") is not None:
        return copy.deepcopy(media["example"]), content_type, field_meta, body_required

    if schema:
        return _full_example_from_schema(schema), content_type, field_meta, body_required

    ref = norm_endpoint.get("_reference_body")
    if ref is not None:
        ct = norm_endpoint.get("_reference_content_type") or content_type
        return copy.deepcopy(ref), ct, field_meta, body_required or True

    return None, content_type, field_meta, body_required


def build_canonical_body(
    norm_endpoint: Optional[dict],
) -> tuple[Any, str, list[dict], bool]:
    """
    Return (body, content_type, field_meta, body_required).
    Preserves full schema shape with all properties (for mutation templates).
    """
    if not norm_endpoint:
        return None, "application/json", [], False

    rb = norm_endpoint.get("requestBody")
    if not rb or not isinstance(rb, dict):
        return None, "application/json", [], False

    content = rb.get("content") or {}
    content_type, media = _pick_content_type(content)
    body_required = bool(rb.get("required"))

    if media.get("example") is not None:
        body = copy.deepcopy(media["example"])
        schema = media.get("schema") or {}
        field_meta = _walk_schema_fields(schema)
        if isinstance(body, dict) and schema.get("properties"):
            full = _full_example_from_schema(schema)
            for key, val in full.items():
                body.setdefault(key, val)
        return body, content_type, field_meta, body_required

    schema = media.get("schema") or {}
    if schema:
        body = _full_example_from_schema(schema)
        field_meta = _walk_schema_fields(schema)
        return body, content_type, field_meta, body_required

    return None, content_type, [], body_required


def _param_sample_value(param: dict) -> str:
    schema = param.get("schema") or {}
    if param.get("example") is not None:
        return str(param["example"])
    if schema.get("example") is not None:
        return str(schema["example"])
    sample = _scalar_example(schema)
    return str(sample) if sample is not None else "test"


def build_reference_request(norm_endpoint: Optional[dict]) -> dict:
    """Build baseline request using exact spec/collection examples."""
    if not norm_endpoint:
        return {}

    method = norm_endpoint.get("method", "GET")
    path = norm_endpoint.get("path", "/")
    headers: dict[str, str] = {"Accept": "application/json"}
    query: dict[str, str] = {}
    path_params: dict[str, str] = {}
    param_fields: list[dict] = []

    for param in norm_endpoint.get("parameters") or []:
        name = param.get("name")
        if not name:
            continue
        schema = param.get("schema") or {}
        sample_str = _param_sample_value(param)
        loc = param.get("in") or "query"
        param_fields.append({
            "path": name,
            "name": name,
            "in": loc,
            "type": schema.get("type", "string"),
            "format": schema.get("format"),
            "enum": schema.get("enum"),
            "required": bool(param.get("required")),
        })
        if loc == "query":
            query[name] = sample_str
        elif loc == "path":
            path_params[name] = sample_str

    body, content_type, field_meta, _ = build_reference_body(norm_endpoint)
    if body is not None and content_type:
        headers["Content-Type"] = content_type

    return {
        "method": method,
        "path": path,
        "headers": headers,
        "query_params": query,
        "path_params": path_params,
        "body": copy.deepcopy(body) if body is not None else None,
        "_field_meta": field_meta + param_fields,
    }


def build_canonical_request(norm_endpoint: Optional[dict]) -> dict:
    """Build a valid baseline request with full body schema shape."""
    if not norm_endpoint:
        return {}

    method = norm_endpoint.get("method", "GET")
    path = norm_endpoint.get("path", "/")
    headers: dict[str, str] = {"Accept": "application/json"}
    query: dict[str, str] = {}
    path_params: dict[str, str] = {}
    param_fields: list[dict] = []

    for param in norm_endpoint.get("parameters") or []:
        name = param.get("name")
        if not name:
            continue
        schema = param.get("schema") or {}
        sample_str = _param_sample_value(param)
        loc = param.get("in") or "query"
        param_fields.append({
            "path": name,
            "name": name,
            "in": loc,
            "type": schema.get("type", "string"),
            "format": schema.get("format"),
            "enum": schema.get("enum"),
            "required": bool(param.get("required")),
        })
        if loc == "query":
            query[name] = sample_str
        elif loc == "path":
            path_params[name] = sample_str

    body, content_type, field_meta, _ = build_canonical_body(norm_endpoint)
    if body is not None and content_type:
        headers["Content-Type"] = content_type

    return {
        "method": method,
        "path": path,
        "headers": headers,
        "query_params": query,
        "path_params": path_params,
        "body": copy.deepcopy(body) if body is not None else None,
        "_field_meta": field_meta + param_fields,
    }


def mutate_field_value(data: Any, field_path: str, new_value: Any) -> Any:
    """Deep copy and set a nested field by dot path (e.g. user.email)."""
    out = copy.deepcopy(data)
    if not field_path:
        return out

    parts = field_path.split(".")
    current = out
    for part in parts[:-1]:
        if isinstance(current, dict):
            if part not in current:
                current[part] = {}
            current = current[part]
        else:
            return out

    last = parts[-1]
    if isinstance(current, dict):
        current[last] = new_value
    return out


def remove_field_key(data: Any, field_path: str) -> Any:
    """Deep copy and remove a key (validation: missing required field)."""
    out = copy.deepcopy(data)
    parts = field_path.split(".")
    current = out
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return out
        current = current[part]
    last = parts[-1]
    if isinstance(current, dict):
        current.pop(last, None)
    return out


def merge_canonical_into_body(existing: Any, canonical: Any) -> Any:
    """Merge missing keys from canonical into existing without removing extras."""
    if not isinstance(canonical, dict):
        return copy.deepcopy(existing if existing is not None else canonical)
    out = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    for key, val in canonical.items():
        if key not in out:
            out[key] = copy.deepcopy(val)
        elif isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = merge_canonical_into_body(out[key], val)
    return out
