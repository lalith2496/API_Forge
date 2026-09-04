"""Lightweight OpenAPI response schema validation."""

from __future__ import annotations

from typing import Any, Optional


def _check_type(value: Any, expected: str) -> Optional[str]:
    mapping = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    if expected not in mapping:
        return None
    py_type = mapping[expected]
    if expected == "integer" and isinstance(value, bool):
        return f"expected integer, got boolean"
    if not isinstance(value, py_type):
        return f"expected {expected}, got {type(value).__name__}"
    return None


def _validate_node(value: Any, schema: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    if not schema:
        return errors

    if "type" in schema:
        err = _check_type(value, schema["type"])
        if err:
            errors.append(f"{path}: {err}")
            return errors

    schema_type = schema.get("type")

    if schema_type == "object" and isinstance(value, dict):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required field missing")
        props = schema.get("properties") or {}
        for key, prop_schema in props.items():
            if key in value and isinstance(prop_schema, dict):
                errors.extend(_validate_node(value[key], prop_schema, f"{path}.{key}"))

    if schema_type == "array" and isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value[:20]):
                errors.extend(_validate_node(item, item_schema, f"{path}[{idx}]"))

    return errors


def validate_against_schema(data: Any, schema: dict) -> tuple[bool, list[str]]:
    """Validate parsed JSON data against a normalized OpenAPI schema dict."""
    if not schema:
        return True, []
    errors = _validate_node(data, schema)
    return len(errors) == 0, errors


def response_schema_for_status(norm_endpoint: dict, status_code: int) -> Optional[dict]:
    """Return normalized JSON schema for a response status code, if documented."""
    responses = norm_endpoint.get("responses") or {}
    resp = responses.get(str(status_code)) or responses.get(str(int(status_code)))
    if not isinstance(resp, dict):
        return None
    content = resp.get("content") or {}
    for media in ("application/json", "application/*+json", "*/*"):
        if media in content:
            schema = (content[media] or {}).get("schema")
            if isinstance(schema, dict):
                return schema
    for media_obj in content.values():
        if isinstance(media_obj, dict):
            schema = media_obj.get("schema")
            if isinstance(schema, dict):
                return schema
    return None
