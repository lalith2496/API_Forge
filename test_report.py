"""Generate HTML/JSON test run reports for browser download."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any


def build_json_report(
    results: list[dict],
    suite_name: str = "API Forge Run",
    meta: dict | None = None,
) -> str:
    payload = {
        "suite_name": suite_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "meta": meta or {},
        "summary": _summary(results),
        "results": results,
    }
    return json.dumps(payload, indent=2, default=str)


def build_html_report(
    results: list[dict],
    suite_name: str = "API Forge Run",
    meta: dict | None = None,
    security_scan: dict | None = None,
) -> str:
    summary = _summary(results)
    rows = []
    for r in results:
        status = "skipped" if r.get("skipped") else (
            "pass" if r.get("passed") else "fail" if r.get("error") else "fail"
        )
        assertions = r.get("assertion_failures") or []
        rows.append(
            f"<tr class='{status}'>"
            f"<td>{html.escape(str(r.get('id', '')))}</td>"
            f"<td>{html.escape(str(r.get('category', '')))}</td>"
            f"<td>{html.escape(str(r.get('description', ''))[:80])}</td>"
            f"<td>{html.escape(str(r.get('expected_status', '')))}</td>"
            f"<td>{html.escape(str(r.get('actual_status', '')))}</td>"
            f"<td>{html.escape(str(r.get('response_time_ms', '')))}</td>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{html.escape('; '.join(assertions) if assertions else (r.get('error') or ''))}</td>"
            f"</tr>"
        )

    meta_rows = ""
    for k, v in (meta or {}).items():
        meta_rows += f"<li><strong>{html.escape(str(k))}:</strong> {html.escape(str(v))}</li>"

    security_section = ""
    if security_scan:
        import security_scanner
        security_section = security_scanner.build_security_report_html(security_scan)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<title>{html.escape(suite_name)} — Test Report</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #0a0a0f; color: #f0f0ff; padding: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
  th, td {{ border: 1px solid #333; padding: 8px; text-align: left; }}
  th {{ background: #14101f; color: #00f5ff; }}
  tr.pass td {{ background: #0a2a0a; }}
  tr.fail td {{ background: #2a0014; }}
  tr.skipped td {{ background: #14101f; color: #888; }}
  .metrics {{ display: flex; gap: 1rem; margin: 1rem 0; }}
  .metric {{ background: #14101f; padding: 1rem; border-radius: 8px; border: 1px solid #00f5ff33; }}
</style></head>
<body>
<h1>{html.escape(suite_name)}</h1>
<p>Generated {html.escape(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))}</p>
<ul>{meta_rows}</ul>
<div class="metrics">
  <div class="metric">Total: {summary['total']}</div>
  <div class="metric">Passed: {summary['passed']}</div>
  <div class="metric">Failed: {summary['failed']}</div>
  <div class="metric">Errors: {summary['error']}</div>
  <div class="metric">Skipped: {summary['skipped']}</div>
</div>
<table>
  <thead><tr>
    <th>ID</th><th>Category</th><th>Description</th><th>Expected</th><th>Got</th>
    <th>Time (ms)</th><th>Result</th><th>Assertions / Error</th>
  </tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>
{security_section}
</body></html>"""


def _summary(results: list[dict]) -> dict[str, Any]:
    return {
        "total": len(results),
        "passed": sum(1 for r in results if r.get("passed") is True),
        "failed": sum(
            1 for r in results
            if r.get("passed") is False and not r.get("skipped") and not r.get("error")
        ),
        "error": sum(1 for r in results if r.get("error")),
        "skipped": sum(1 for r in results if r.get("skipped")),
    }
