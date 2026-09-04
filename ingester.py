# an ingester will accept yaml/json files.
# these will be OpenAPI specs files in different formats

# it will spit out a normalized output which will be same irrespective of the
# file format

import json
import yaml
from pathlib import Path
from typing import Optional

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _decode_json_pointer_segment(segment: str) -> str:
    """Decode RFC 6901 JSON Pointer segment (~0 -> ~, ~1 -> /)."""
    return segment.replace("~1", "/").replace("~0", "~")


def _parse_stream(ext: str, stream):
    """Parse YAML or JSON from a file-like object."""
    if ext in (".yml", ".yaml"):
        return yaml.safe_load(stream)
    if ext == ".json":
        return json.load(stream)
    raise ValueError("Unsupported file format, not an OpenAPI spec.")


def Parse(filename):
    """Parse an OpenAPI spec from a filesystem path."""
    path = Path(filename)
    ext = path.suffix.lower()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _parse_stream(ext, f)
    except (FileNotFoundError, json.JSONDecodeError, yaml.YAMLError, ValueError) as e:
        return {"error": str(e)}


def ParseFile(f):
    """Parse an OpenAPI spec from a Streamlit UploadedFile."""
    ext = Path(f.name).suffix.lower()
    try:
        return _parse_stream(ext, f)
    except (json.JSONDecodeError, yaml.YAMLError, ValueError) as e:
        return {"error": str(e)}


def ResolveRef(content, ref):
    """
    Resolve an internal JSON Pointer $ref (#/...) within the spec document.
    """
    if not content or not ref:
        return {"error": "content or ref is not right."}
    if not ref.startswith("#/"):
        return {"error": f"External or unsupported $ref: {ref}"}

    segments = [_decode_json_pointer_segment(s) for s in ref[2:].split("/") if s]
    if not segments:
        return {"error": "Empty JSON pointer in $ref"}

    refined = content
    for level in segments:
        if not isinstance(refined, dict):
            return {"error": f"Schema not found at segment '{level}'"}
        if level not in refined:
            return {"error": f"Schema not found: {ref}"}
        refined = refined[level]

    return refined


def _resolve_path_item(spec, path_data):
    """Resolve path-level $ref; return a dict or None."""
    if not isinstance(path_data, dict):
        return None
    if "$ref" in path_data:
        path_data = ResolveRef(spec, path_data["$ref"])
    if isinstance(path_data, dict) and "error" in path_data:
        return None
    return path_data if isinstance(path_data, dict) else None


def ListEndpoints(content):
    """List all API endpoints from a parsed OpenAPI spec."""
    if not isinstance(content, dict):
        return [{"error": "Parsed content is not a dictionary object"}]

    paths = content.get("paths")
    if not paths or not isinstance(paths, dict):
        return [{"error": "No endpoint found"}]

    endpts = []
    for path, raw_path_data in paths.items():
        path_data = _resolve_path_item(content, raw_path_data)
        if not path_data:
            continue

        for method, method_data in path_data.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(method_data, dict):
                continue

            endpts.append({
                "path": path,
                "method": method.upper(),
                "summary": method_data.get("summary", ""),
                "operationId": method_data.get("operationId", ""),
                "responses": list(method_data.get("responses", {}).keys()),
            })

    if not endpts:
        return [{"error": "No endpoint found"}]
    return endpts


def endpoint_label(ep, index, label_counts):
    """Human-readable label; disambiguate duplicate method+path pairs."""
    base = f"{ep['method']} {ep['path']}"
    op_id = ep.get("operationId") or ""
    if op_id:
        return f"{base} — {op_id}"
    if label_counts.get(base, 0) > 1:
        return f"{base} — #{index + 1}"
    return base


def ResolveServers(spec):
    """Resolve servers from OpenAPI 3 or Swagger 2."""
    servers = spec.get("servers")
    if servers:
        return servers

    if spec.get("swagger"):
        host = spec.get("host", "")
        base_path = spec.get("basePath", "") or ""
        schemes = spec.get("schemes") or ["https"]
        if host:
            return [
                {"url": f"{scheme}://{host}{base_path}".rstrip("/") or f"{scheme}://{host}"}
                for scheme in schemes
            ]
    return []


def ListSchemas(content):
    """List all defined schemas from the spec file."""
    if not isinstance(content, dict):
        return [{"error": "Not a valid parsed input"}]

    components = content.get("components", {})
    schemas = components.get("schemas", {})

    if not schemas:
        return [{"error": "No schema defined"}]

    return schemas


def NormalizeSchema(content, schema, visited_refs=None):
    """
    Normalize a schema into a single consistent format.
    Handles $ref (with cycle detection), allOf/anyOf/oneOf, and nesting.
    """
    if visited_refs is None:
        visited_refs = set()

    if not schema:
        return {"error": "No schema provided"}

    if isinstance(schema, dict) and "error" in schema:
        return schema

    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in visited_refs:
            return {"$ref": ref, "circular": True}
        visited_refs = visited_refs | {ref}
        resolved = ResolveRef(content, ref)
        if isinstance(resolved, dict) and "error" in resolved:
            return resolved
        schema = resolved

    if not isinstance(schema, dict):
        return {"error": "Schema is not an object"}

    result = {
        "type": schema.get("type"),
        "format": schema.get("format"),
        "required": schema.get("required", []),
        "properties": {},
        "items": None,
        "enum": schema.get("enum", []),
        "minimum": schema.get("minimum"),
        "maximum": schema.get("maximum"),
        "minLength": schema.get("minLength"),
        "maxLength": schema.get("maxLength"),
        "allOf": [],
        "anyOf": [],
        "oneOf": [],
    }

    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema and isinstance(schema[keyword], list):
            result[keyword] = [
                NormalizeSchema(content, sub, visited_refs)
                for sub in schema[keyword]
            ]

    if "properties" in schema and isinstance(schema["properties"], dict):
        for name, prop_schema in schema["properties"].items():
            result["properties"][name] = NormalizeSchema(
                content, prop_schema, visited_refs
            )

    if "items" in schema:
        result["items"] = NormalizeSchema(content, schema["items"], visited_refs)

    return result


def NormalizePara(spec, params):
    out = []
    for p in params or []:
        if not isinstance(p, dict):
            continue
        if "$ref" in p:
            p = ResolveRef(spec, p["$ref"])
            if isinstance(p, dict) and "error" in p:
                continue

        out.append({
            "name": p.get("name"),
            "in": p.get("in"),
            "required": p.get("required", False),
            "description": p.get("description", ""),
            "schema": NormalizeSchema(spec, p.get("schema")),
            "example": p.get("example"),
        })
    return out


def NormalizeSecurity(content, security_list):
    schemes = content.get("components", {}).get("securitySchemes", {})
    if not schemes and content.get("swagger"):
        schemes = content.get("securityDefinitions", {})
    out = []

    for sec in security_list or []:
        if not isinstance(sec, dict):
            continue
        for scheme_name, scopes in sec.items():
            scheme = schemes.get(scheme_name, {})
            out.append({
                "name": scheme_name,
                "type": scheme.get("type"),
                "scheme": scheme.get("scheme"),
                "bearerFormat": scheme.get("bearerFormat"),
                "in": scheme.get("in"),
                "parameterName": scheme.get("name"),
                "flows": scheme.get("flows"),
                "scopes": scopes,
            })
    return out


def NormalizeResponse(spec, response):
    if not isinstance(response, dict):
        return {"description": "", "content": {}}

    if "$ref" in response:
        response = ResolveRef(spec, response["$ref"])
        if isinstance(response, dict) and "error" in response:
            return {"description": response["error"], "content": {}}

    content = response.get("content", {})
    normalized_content = {}

    for content_type, media in content.items():
        if not isinstance(media, dict):
            continue
        normalized_content[content_type] = {
            "schema": NormalizeSchema(spec, media.get("schema")),
            "example": media.get("example"),
        }

    return {
        "description": response.get("description", ""),
        "content": normalized_content,
    }


def NormalizeEndpoint(spec, path, method):
    method = method.lower()
    raw_path_item = spec.get("paths", {}).get(path, {})
    path_item = _resolve_path_item(spec, raw_path_item)
    if not path_item:
        return {"error": f"Path not found or invalid: {path}"}

    operation = path_item.get(method)
    if not isinstance(operation, dict):
        return {"error": f"Endpoint not found: {method.upper()} {path}"}

    params = []
    params.extend(NormalizePara(spec, path_item.get("parameters", [])))
    params.extend(NormalizePara(spec, operation.get("parameters", [])))

    request_body = None
    if operation.get("requestBody"):
        rb = operation["requestBody"]
        if isinstance(rb, dict) and "$ref" in rb:
            rb = ResolveRef(spec, rb["$ref"])
            if isinstance(rb, dict) and "error" in rb:
                rb = {}

        if isinstance(rb, dict):
            request_body = {
                "required": rb.get("required", False),
                "description": rb.get("description", ""),
                "content": {},
            }
            for content_type, media in rb.get("content", {}).items():
                if not isinstance(media, dict):
                    continue
                request_body["content"][content_type] = {
                    "schema": NormalizeSchema(spec, media.get("schema")),
                    "example": media.get("example"),
                }

    responses = {}
    for code, resp in operation.get("responses", {}).items():
        responses[str(code)] = NormalizeResponse(spec, resp)

    security = operation.get("security", spec.get("security", []))
    normalized_security = NormalizeSecurity(spec, security)

    return {
        "openapi": spec.get("openapi"),
        "info": spec.get("info", {}),
        "servers": ResolveServers(spec),
        "path": path,
        "method": method.upper(),
        "summary": operation.get("summary", ""),
        "description": operation.get("description", ""),
        "operationId": operation.get("operationId", ""),
        "tags": operation.get("tags", []),
        "security": normalized_security,
        "parameters": params,
        "requestBody": request_body,
        "responses": responses,
    }


def endpoint_key(ep):
    """Stable key for session state / cache invalidation."""
    parts = [ep["method"], ep["path"]]
    if ep.get("operationId"):
        parts.append(ep["operationId"])
    return ":".join(parts)


def norm_lookup_keys(ep: dict, norm_map: Optional[dict] = None) -> set[str]:
    """All norm_map keys that refer to the same method+path endpoint."""
    keys = {endpoint_key(ep), f"{ep['method']}:{ep['path']}"}
    prefix = f"{ep['method']}:{ep['path']}:"
    for key in (norm_map or {}):
        if key == f"{ep['method']}:{ep['path']}" or key.startswith(prefix):
            keys.add(key)
    return keys


def lookup_norm(norm_map: Optional[dict], ep: dict) -> Optional[dict]:
    """
    Resolve normalized endpoint metadata even when operationId differs
    between the suite and norm_map keys.
    """
    if not norm_map or not ep:
        return None

    direct = norm_map.get(endpoint_key(ep))
    if direct:
        return direct

    base = f"{ep['method']}:{ep['path']}"
    if base in norm_map:
        return norm_map[base]

    prefix = base + ":"
    for key, norm in norm_map.items():
        if key.startswith(prefix):
            return norm

    return None


def selection_key(endpoints):
    """Stable key for a multi-endpoint selection."""
    ans = "|".join(sorted(endpoint_key(ep) for ep in endpoints))
    return ans


_MAX_DESC = 120
_MAX_SCHEMA_DEPTH = 2


def _truncate(text, max_len=_MAX_DESC):
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def CompactSchema(schema, depth=0):
    """Token-minimized schema for LLM prompts (from normalized schema dict)."""
    if not schema or not isinstance(schema, dict):
        return {}
    if "error" in schema:
        return {"error": True}
    if schema.get("circular"):
        return {"$ref": schema.get("$ref", "circular")}
    if depth >= _MAX_SCHEMA_DEPTH:
        return {
            "type": schema.get("type"),
            "composed": bool(
                schema.get("allOf") or schema.get("anyOf") or schema.get("oneOf")
            ),
        }

    out = {}
    for key in (
        "type", "format", "enum", "minimum", "maximum", "minLength", "maxLength"
    ):
        val = schema.get(key)
        if val is not None and val != []:
            out[key] = val
    if schema.get("required"):
        out["required"] = schema["required"]
    if schema.get("allOf") or schema.get("anyOf") or schema.get("oneOf"):
        out["composed"] = True
    if isinstance(schema.get("properties"), dict):
        out["properties"] = {
            name: CompactSchema(prop, depth + 1)
            for name, prop in schema["properties"].items()
        }
    if schema.get("items"):
        out["items"] = CompactSchema(schema["items"], depth + 1)
    return out


def CompactEndpoint(full_norm):
    """Strip a full normalized endpoint down for LLM consumption."""
    desc = full_norm.get("description") or full_norm.get("summary") or ""

    parameters = []
    for param in full_norm.get("parameters") or []:
        parameters.append({
            "name": param.get("name"),
            "in": param.get("in"),
            "required": param.get("required", False),
            "schema": CompactSchema(param.get("schema") or {}),
        })

    request_body = None
    rb = full_norm.get("requestBody")
    if rb:
        properties = {}
        content = rb.get("content") or {}
        for media in content.values():
            if not isinstance(media, dict):
                continue
            schema = media.get("schema") or {}
            if isinstance(schema.get("properties"), dict):
                for name, prop in schema["properties"].items():
                    properties[name] = CompactSchema(prop)
        request_body = {
            "required": rb.get("required", False),
            "content_types": list(content.keys()),
            "properties": properties,
        }

    responses = []
    for code, resp in (full_norm.get("responses") or {}).items():
        responses.append({
            "code": str(code),
            "description": _truncate(resp.get("description", ""), 80),
        })

    security = []
    for sec in full_norm.get("security") or []:
        if not isinstance(sec, dict):
            continue
        security.append({
            "type": sec.get("type"),
            "scheme": sec.get("scheme"),
            "name": sec.get("name"),
        })

    compact = {
        "method": full_norm.get("method"),
        "path": full_norm.get("path"),
        "summary": _truncate(desc),
        "parameters": parameters,
        "responses": responses,
        "security": security,
    }
    if full_norm.get("operationId"):
        compact["operationId"] = full_norm["operationId"]
    if request_body:
        compact["requestBody"] = request_body
    return compact


def NormalizeEndpoints(spec, endpoint_list):
    """Normalize multiple endpoints; returns {endpoint_key: full_norm}."""
    norm_map = {}
    for ep in endpoint_list:
        norm = NormalizeEndpoint(spec, ep["path"], ep["method"])
        if isinstance(norm, dict) and "error" in norm:
            continue
        norm_map[endpoint_key(ep)] = norm
    return norm_map


def BuildLLMPayload(spec, selected_endpoints, norm_map):
    """Build compact multi-endpoint payload for the LLM."""
    info = spec.get("info") or {}
    servers = ResolveServers(spec)
    if norm_map:
        first = next(iter(norm_map.values()))
        servers = first.get("servers") or servers

    endpoints = []
    for ep in selected_endpoints:
        full = norm_map.get(endpoint_key(ep))
        if full:
            endpoints.append(CompactEndpoint(full))

    return {
        "api": {"title": info.get("title", ""), "servers": servers},
        "endpoints": endpoints,
    }
