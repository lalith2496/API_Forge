"""Sanitize LLM-generated response_assertions against the API spec."""

from __future__ import annotations

import copy
import re
from typing import Any, Optional

import ingester
import schema_validator

_SAFE_STRING_ASSERTIONS = (
    "valid json",
    "not empty",
    "non-empty",
    "nonempty",
    "content-type",
    "response time",
)

_HAPPY_CATEGORIES = frozenset({"happy_path", "response_schema"})


def _schema_field_names(schema: Optional[dict]) -> set[str]:
    if not schema or not isinstance(schema, dict):
        return set()
    names: set[str] = set()

    def _walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        props = node.get("properties")
        if isinstance(props, dict):
            names.update(props.keys())
        for key in ("items", "allOf", "anyOf", "oneOf"):
            val = node.get(key)
            if isinstance(val, dict):
                _walk(val)
            elif isinstance(val, list):
                for item in val:
                    _walk(item)

    _walk(schema)
    return names


def _is_safe_string_assertion(text: str) -> bool:
    lower = (text or "").lower()
    return any(token in lower for token in _SAFE_STRING_ASSERTIONS)


def _keep_string_assertion(text: str, schema_fields: set[str]) -> bool:
    if _is_safe_string_assertion(text):
        return True

    lower = (text or "").lower()
    if "field" in lower or "property" in lower or "key" in lower:
        quoted = re.findall(r"""['"]([^'"]+)['"]""", text)
        if quoted:
            return quoted[0] in schema_fields if schema_fields else False
        return False

    # Reject vague natural-language field guesses like "contains article data".
    if any(word in lower for word in ("contains", "includes", "has")):
        return False

    return not schema_fields


def sanitize_response_assertions(test_suite: dict, norm_map: Optional[dict]) -> dict:
    """Drop hallucinated field assertions not backed by the response schema."""
    if not norm_map or not isinstance(test_suite, dict):
        return test_suite

    suite = copy.deepcopy(test_suite)
    for case in suite.get("test_cases") or []:
        expected = case.setdefault("expected", {})
        raw = expected.get("response_assertions") or []
        if not raw:
            continue

        ep = case.get("endpoint") or {}
        norm = ingester.lookup_norm(norm_map, ep)
        status = expected.get("status_code")
        schema = (
            schema_validator.response_schema_for_status(norm, status)
            if norm and status is not None
            else None
        )
        schema_fields = _schema_field_names(schema)
        category = case.get("category") or ""

        cleaned = []
        for item in raw:
            if isinstance(item, dict):
                cleaned.append(item)
                continue
            if not isinstance(item, str):
                continue
            if _keep_string_assertion(item, schema_fields):
                cleaned.append(item)

        if category in _HAPPY_CATEGORIES and not cleaned:
            cleaned = ["response is valid JSON"]

        status = expected.get("status_code")
        if status is not None and status >= 400 and category in (
            "auth", "validation", "boundary", "security", "optional_fields",
        ):
            cleaned = [
                a for a in cleaned
                if not (isinstance(a, str) and "valid json" in a.lower())
            ]

        expected["response_assertions"] = cleaned

    return suite
