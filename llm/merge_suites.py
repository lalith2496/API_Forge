"""Merge multiple LLM-generated test suites into one validated suite."""

from __future__ import annotations

from llm.base import validate_test_suite


def merge_suites(*suites: dict) -> dict:
    """Merge test cases from multiple suites; dedupe by id, renumber if needed."""
    merged = {
        "test_suite_name": "",
        "endpoints": [],
        "test_cases": [],
    }
    seen_endpoints = set()
    seen_ids = set()

    for suite in suites:
        if not isinstance(suite, dict) or "error" in suite:
            continue
        if not merged["test_suite_name"] and suite.get("test_suite_name"):
            merged["test_suite_name"] = suite["test_suite_name"]
        for ep in suite.get("endpoints") or []:
            key = (str(ep.get("method", "")).upper(), str(ep.get("path", "")))
            if key not in seen_endpoints:
                merged["endpoints"].append(ep)
                seen_endpoints.add(key)
        for case in suite.get("test_cases") or []:
            cid = case.get("id")
            if cid and cid not in seen_ids:
                merged["test_cases"].append(case)
                seen_ids.add(cid)

    for idx, case in enumerate(merged["test_cases"], start=1):
        case["id"] = f"TC-{idx:02d}"

    return merged
