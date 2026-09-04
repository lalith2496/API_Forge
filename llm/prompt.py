import json


def build_multi_prompt(
    llm_payload: dict,
    max_cases: int = 20,
    focus: str = "full",
) -> str:
    """
    Build LLM prompt from compact multi-endpoint payload.

    focus:
      - full: balanced coverage up to max_cases
      - core: happy_path + auth only (multi-pass pass 1)
      - negative: validation + boundary + optional_fields (multi-pass pass 2)
      - security: SQLi/XSS/auth/enum/oversized/broken-ID cases (pass 3)
      - rfc: RFC 9110/7807/6265 semantics (pass 4)
    """
    max_cases = max(10, min(int(max_cases or 20), 50))
    endpoints = llm_payload.get("endpoints") or []
    n_ep = max(len(endpoints), 1)
    per_ep = max(6, max_cases // n_ep)
    min_cases = min(max_cases, max(8, per_ep * n_ep))
    payload_json = json.dumps(llm_payload, separators=(",", ":"))

    categories = (
        "happy_path|auth|validation|boundary|optional_fields|response_schema|"
        "security|rfc_semantics|rfc_problem|rfc_cookies|rate_limit"
    )

    if focus == "core":
        category_rule = (
            "- Generate ONLY happy_path and auth category tests in this pass.\n"
            f"- Target {min_cases} to {max_cases} test cases focused on success paths and auth.\n"
            "- EXACTLY ONE happy_path per endpoint — the canonical success request from the spec.\n"
            "- Do NOT label auth tests (missing/invalid token, missing key) as happy_path — use category auth.\n"
            "- happy_path request body MUST be the EXACT example from spec/collection — no extra fields.\n"
            "- happy_path MUST NOT include query/path params unless declared in the OpenAPI spec.\n"
            "- Extra or unsupported query params belong in validation category with expected status_code 400.\n"
        )
    elif focus == "negative":
        category_rule = (
            "- Generate ONLY validation, boundary, optional_fields, and response_schema tests.\n"
            "- Do NOT include happy_path cases in this pass — they are merged from a prior pass.\n"
            "- Do NOT repeat happy_path tests already covered.\n"
            f"- Target {min_cases} to {max_cases} negative/edge test cases.\n"
            "- Each endpoint MUST have at least 2 validation OR boundary cases.\n"
            "- Unsupported/extra query or path params MUST expect status_code 400.\n"
            "- Null, empty, or wrong-type request bodies MUST expect status_code 400.\n"
            "- Keep the same JSON object shape as the spec; change VALUES only for negative tests.\n"
        )
    elif focus == "security":
        category_rule = (
            "- Generate ONLY security category tests in this pass.\n"
            "- Do NOT include happy_path — merged from prior pass.\n"
            "- Include: missing required fields, invalid enums, SQL injection strings, XSS payloads, "
            "oversized strings, invalid date formats, auth failures, broken object IDs.\n"
            "- Keep request body JSON shape identical to spec; mutate values only.\n"
            f"- Target {min_cases} to {max_cases} security test cases.\n"
        )
    elif focus == "rfc":
        category_rule = (
            "- Generate ONLY rfc_semantics, rfc_problem, and rfc_cookies category tests.\n"
            "- Do NOT include happy_path — merged from prior pass.\n"
            "- RFC 9110: wrong method (405), bad Accept (406), wrong Content-Type (415).\n"
            "- RFC 7807: error responses should use application/problem+json with type, title, status.\n"
            "- RFC 6265: cookie/auth endpoints — test Set-Cookie expectations.\n"
            f"- Target {min_cases} to {max_cases} RFC-aware test cases.\n"
        )
    else:
        category_rule = (
            f"- You MUST return at least {min_cases} test cases and at most {max_cases}.\n"
            "- Aim for the upper end of the range — do not stop at 10 unless the API is trivial.\n"
            "- Category mix (required): at least 30% validation + boundary + auth + security combined.\n"
            "- Per endpoint: minimum 1 happy_path, 1 validation OR boundary, auth if secured, 1 security if inputs exist.\n"
            "- happy_path MUST use the EXACT request body from spec/collection examples.\n"
            "- happy_path query/path params MUST come ONLY from OpenAPI spec parameters — "
            "never add params from Postman/cURL unless declared in the spec.\n"
        )

    extra_categories = ""
    if max_cases >= 35 and focus == "full":
        extra_categories = (
            "- Add idempotency, pagination, sort/filter, and concurrency-safe read-only checks where applicable.\n"
            "- Include rfc_semantics and security cases where HTTP semantics or injection apply.\n"
        )

    rfc_block = """
RFC rules (when applicable):
- RFC 9110: use correct method, Accept, Content-Type; expect 405/406/415 for violations.
- RFC 7807: 4xx/5xx error responses may use application/problem+json with type, title, status fields.
- RFC 6265: auth/session endpoints may return Set-Cookie; note expected Secure/HttpOnly flags in notes.
"""

    prompt = f"""
You are an expert API test designer.

CRITICAL — test count (highest priority):
- Return between {min_cases} and {max_cases} test cases total across ALL endpoints.
- HARD MINIMUM: {min_cases} test cases. HARD MAXIMUM: {max_cases} test cases.
- Scale per-endpoint coverage: at least {per_ep} cases per endpoint when the API supports it ({n_ep} endpoint(s) selected).
- Every endpoint MUST have at least 1 happy_path test case (except security/rfc-only passes).
- Test case IDs must be unique globally: TC-01, TC-02, …
- Do NOT return fewer than {min_cases} test cases unless the API truly has only one trivial endpoint.
- Return valid JSON only. No JavaScript syntax.

{category_rule}

Return ONLY valid JSON matching this schema:
{{
  "test_suite_name": string,
  "endpoints": [{{"method": string, "path": string}}],
  "test_cases": [
    {{
      "id": "TC-01",
      "endpoint": {{"method": string, "path": string}},
      "category": "{categories}",
      "description": string,
      "requires_user_input": boolean,
      "user_inputs": {{ "<field_name>": "<why the user must supply this>" }},
      "request": {{
        "method": string,
        "path": string,
        "headers": object,
        "query_params": object,
        "path_params": object,
        "body": object|null
      }},
      "expected": {{
        "status_code": number,
        "response_assertions": [string]
      }},
      "notes": string
    }}
  ]
}}

Compact API payload (endpoints + shared metadata):
{payload_json}

Rules:
- test_cases.length MUST be >= {min_cases} AND <= {max_cases}.
- Include every endpoint in the endpoints array.
- Each test case MUST match a provided endpoint (same method + path).
- Use only fields present in the compact endpoint data.
- If auth/security exists, include missing/invalid/expired token tests when applicable.
- For POST/PUT/PATCH/DELETE with requestBody, happy_path MUST use the EXACT request body from the spec/collection example — do not add extra fields.
- All non-happy_path POST/PUT/PATCH/DELETE body variations are invalid payloads and MUST expect status_code 400.
- Invalid request payload cases (missing fields, wrong types, malformed JSON) MUST expect status_code 400.
- GET query/path param invalid values (wrong type, bad enum, invalid IDs) MUST expect status_code 400.
- response_assertions: use ONLY "response is valid JSON" unless the response schema explicitly defines a field — never guess field names like "article".
- Cover required fields, boundaries, and wrong-type tests where possible.
- Auth placeholders: VALID_TOKEN for Bearer Authorization only; API_KEY for api-key header schemes (e.g. Key). Never put VALID_TOKEN in API key headers.
- For GET endpoints with query or path params, use USER_INPUT:<paramName> when the user must supply real values.
{rfc_block}
{extra_categories}
Test data strategy:
A) Use concrete literals for generic happy paths when possible.
B) Use USER_INPUT:<field_name> when the user must supply tenant-specific values (IDs, filters, search terms).
C) Negative/security tests: invalid values matching parameter type; preserve object keys.

Before responding, COUNT test_cases.length — it must be >= {min_cases}. Every endpoint needs >= 1 happy_path (except security/rfc-only passes).
"""
    return prompt
