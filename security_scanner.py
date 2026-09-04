"""Post-run HTTP security scanner (response headers, CORS, cookies, RFC 7807)."""

from __future__ import annotations

import json
from typing import Optional

import rfc_assertions

RECOMMENDED_HEADERS = (
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "content-security-policy",
)


def _severity_for(rule_id: str) -> str:
    if rule_id.startswith("cors_") or rule_id.startswith("cookie_"):
        return "high"
    if rule_id.startswith("header_missing_"):
        return "medium"
    return "info"


def scan_run_results(
    run_results: list[dict],
    environment: str = "DEV",
) -> dict:
    """
    Analyze run results for security findings.
    Returns {findings, score, summary, environment}.
    """
    findings = []

    for result in run_results or []:
        if result.get("skipped"):
            continue
        case_id = result.get("id", "?")
        category = result.get("category", "")
        status = result.get("actual_status")
        headers = {k.lower(): v for k, v in (result.get("response_headers") or {}).items()}

        if category in ("happy_path", "response_schema") and status and status < 400:
            for hdr in RECOMMENDED_HEADERS:
                if hdr not in headers:
                    findings.append({
                        "severity": _severity_for(f"header_missing_{hdr}"),
                        "rule_id": f"header_missing_{hdr}",
                        "case_id": case_id,
                        "detail": f"Missing recommended security header: {hdr}",
                    })

            acao = headers.get("access-control-allow-origin", "")
            acac = headers.get("access-control-allow-credentials", "").lower()
            if acao == "*" and acac == "true":
                findings.append({
                    "severity": "high",
                    "rule_id": "cors_wildcard_credentials",
                    "case_id": case_id,
                    "detail": "CORS allows * origin with credentials",
                })
            elif acao == "*":
                findings.append({
                    "severity": "medium",
                    "rule_id": "cors_wildcard_origin",
                    "case_id": case_id,
                    "detail": "CORS Access-Control-Allow-Origin is *",
                })

            set_cookie = headers.get("set-cookie", "")
            if set_cookie and category == "rfc_cookies":
                flags = rfc_assertions.parse_set_cookie_flags(set_cookie)
                if not flags["secure"]:
                    findings.append({
                        "severity": "high",
                        "rule_id": "cookie_missing_secure",
                        "case_id": case_id,
                        "detail": "Set-Cookie missing Secure flag",
                    })
                if not flags["httponly"]:
                    findings.append({
                        "severity": "high",
                        "rule_id": "cookie_missing_httponly",
                        "case_id": case_id,
                        "detail": "Set-Cookie missing HttpOnly flag",
                    })

        if status and status >= 400 and category in ("validation", "security", "rfc_problem", "boundary"):
            ct = headers.get("content-type", "")
            body = result.get("response_body") or ""
            if "application/problem+json" in ct or category == "rfc_problem":
                ok, msg = rfc_assertions.evaluate_rfc_assertion(
                    {"type": "problem_json"},
                    body,
                    status,
                    result.get("response_headers") or {},
                )
                if not ok:
                    findings.append({
                        "severity": "medium",
                        "rule_id": "rfc7807_invalid",
                        "case_id": case_id,
                        "detail": msg,
                    })

    high = sum(1 for f in findings if f["severity"] == "high")
    medium = sum(1 for f in findings if f["severity"] == "medium")
    score = max(0, 100 - high * 15 - medium * 5 - len(findings))

    summary = f"{len(findings)} finding(s): {high} high, {medium} medium"
    if environment == "PROD" and high > 0:
        summary += " — review before PROD release"

    return {
        "findings": findings,
        "score": score,
        "summary": summary,
        "environment": environment,
    }


def build_security_report_html(scan: dict) -> str:
    """HTML fragment for security scan results."""
    rows = []
    for f in scan.get("findings") or []:
        rows.append(
            f"<tr class='{f['severity']}'>"
            f"<td>{f['severity']}</td>"
            f"<td>{f['rule_id']}</td>"
            f"<td>{f['case_id']}</td>"
            f"<td>{f['detail']}</td>"
            f"</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='4'>No findings</td></tr>"
    return f"""
<h2>Security Scan — {scan.get('environment', 'DEV')}</h2>
<p>Score: {scan.get('score', 0)}/100 — {scan.get('summary', '')}</p>
<table border='1' cellpadding='6' style='border-collapse:collapse;width:100%'>
<thead><tr><th>Severity</th><th>Rule</th><th>Case</th><th>Detail</th></tr></thead>
<tbody>{body}</tbody>
</table>
"""


def build_security_report_json(scan: dict) -> str:
    return json.dumps(scan, indent=2)
