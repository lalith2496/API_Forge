import json
import pandas as pd
import streamlit as st
import ingester

from llm import prompt
from llm import merge_suites
from llm.provider_registry import get_provider, get_avl_providers
import pytest_exporter
import postman_exporter
import user_inputs
import api_doc_redoc
import runner
import test_report
import spec_bodies
import curl_parser
import postman_importer
import negative_generator
import security_generator
import rfc_generator
import assertion_sanitizer
import case_normalizer
import id_cases
import invalid_payload_cases
import invalid_value_cases
import parameter_discovery
import auth_helpers
import importlib

if not hasattr(auth_helpers, "inject_spec_auth_headers"):
    auth_helpers = importlib.reload(auth_helpers)

import security_scanner
import environment_profiles
from ui import components as ui

st.set_page_config(page_title="API Forge", page_icon="⚒", layout="wide")

ui.inject_theme()
ui.render_hero()


# ── Helpers (unchanged) ───────────────────────────────────────────────────
@st.cache_data(show_spinner="Prepping exports…")
def _temp_exports(raw_json: str, norm_map_json: str, values_json: str):
    raw_cases = json.loads(raw_json)
    norm_map  = json.loads(norm_map_json)
    values    = json.loads(values_json)
    display_cases = user_inputs.apply_user_inputs(raw_cases, values)
    env           = pytest_exporter.BuildEnvFile(norm_map, test_suite=raw_cases, user_values=values)
    pytest_test   = pytest_exporter.BuildPytestFile(raw_cases, user_input_defaults=values, norm_endpt_or_map=norm_map)
    postman_col   = postman_exporter.BuildPostmanCollection(raw_cases, norm_map, user_values=values)
    return (
        json.dumps(display_cases, indent=2),
        env,
        pytest_test,
        json.dumps(postman_col, indent=2),
    )

@st.cache_data(ttl=300, show_spinner="Fetching models…")
def _list_models_cached(provider_name: str) -> list:
    prov = get_provider(provider_name)
    if not prov.is_configured():
        return []
    try:
        models = prov.list_models()
        return [m for m in models if isinstance(m, list) and len(m) == 2]
    except Exception:
        return []

def _file_fingerprint(uploaded) -> str:
    return f"{uploaded.name}:{uploaded.size}"

def _stable_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)

def _load_parsed_spec(uploaded):
    fp = _file_fingerprint(uploaded)
    if st.session_state.get("_spec_fp") != fp:
        st.session_state._spec_fp   = fp
        st.session_state._spec_data = ingester.ParseFile(uploaded)
        st.session_state.pop("_norm_map_key", None)
        st.session_state.pop("_norm_map",     None)
    return st.session_state._spec_data

def _load_norm_map(data, selected_endpts, selection_key):
    if st.session_state.get("_norm_map_key") != selection_key:
        st.session_state._norm_map_key = selection_key
        st.session_state._norm_map     = ingester.NormalizeEndpoints(data, selected_endpts)
    return st.session_state._norm_map

def _generate_test_suite(provider, model: str, llm_payload: dict, max_cases: int) -> dict:
    """
    Fast LLM generation: one core pass (happy + auth).
    Rule-based finalize adds validation, security, RFC, and invalid-value cases.
    """
    endpoints = llm_payload.get("endpoints") or []
    n_ep = max(len(endpoints), 1)
    llm_target = min(max_cases, max(10, 6 * n_ep))

    result = provider.generate_result(
        model=model,
        prompt=prompt.build_multi_prompt(
            llm_payload,
            max_cases=llm_target,
            focus="core",
        ),
    )
    return result

def _finalize_test_suite(cases: dict, norm_map: dict, imported_cases: list | None = None) -> dict:
    """Inject spec bodies and add missing negative/security/RFC cases from the API spec."""
    if not isinstance(cases, dict) or "error" in cases:
        return cases
    norm_map = parameter_discovery.build_effective_norm_map(
        cases, norm_map, imported_cases=imported_cases
    )
    cases = case_normalizer.normalize_generated_cases(cases, norm_map)
    cases = auth_helpers.inject_spec_auth_headers(cases, norm_map)
    cases = spec_bodies.inject_spec_bodies(cases, norm_map)
    cases = negative_generator.supplement_negative_cases(cases, norm_map)
    cases = security_generator.supplement_security_cases(cases, norm_map)
    cases = rfc_generator.supplement_rfc_cases(cases, norm_map)
    cases = id_cases.supplement_invalid_id_cases(
        cases, norm_map, negative_generator._base_request
    )
    cases = invalid_value_cases.supplement_invalid_value_cases(
        cases, norm_map, negative_generator._base_request
    )
    cases = invalid_payload_cases.supplement_invalid_payload_cases(
        cases, norm_map, negative_generator._base_request
    )
    cases = spec_bodies.enforce_payload_expectations(cases, norm_map)
    cases = spec_bodies.enforce_spec_deviation_expectations(cases, norm_map)
    cases = assertion_sanitizer.sanitize_response_assertions(cases, norm_map)
    return cases

def _build_import_only_suite(selected_endpts, imported_cases, title):
    """Build a test suite from imported Postman/cURL requests."""
    import copy
    selected_keys = {ingester.endpoint_key(ep) for ep in selected_endpts}
    cases = copy.deepcopy([
        c for c in (imported_cases or [])
        if ingester.endpoint_key(c.get("endpoint") or {}) in selected_keys
    ])
    for idx, case in enumerate(cases, start=1):
        case["id"] = f"TC-{idx:02d}"
    return {
        "test_suite_name": title or "Imported requests",
        "endpoints": [{"method": ep["method"], "path": ep["path"]} for ep in selected_endpts],
        "test_cases": cases,
    }

def _rerun_request_overrides(prefix: str, default_req: dict) -> dict:
    """Read per-case rerun overrides from session widget keys."""
    overrides: dict = {}
    body_text = str(st.session_state.get(f"{prefix}_body", "") or "").strip()
    if body_text:
        try:
            overrides["body"] = json.loads(body_text)
        except json.JSONDecodeError:
            overrides["body"] = body_text

    headers_text = str(st.session_state.get(f"{prefix}_headers", "") or "").strip()
    if headers_text:
        try:
            parsed = json.loads(headers_text)
            if isinstance(parsed, dict):
                overrides["headers"] = parsed
        except json.JSONDecodeError:
            pass

    query_overrides = {}
    for key in (default_req.get("query_params") or {}):
        widget_val = st.session_state.get(f"{prefix}_q_{key}")
        if widget_val is not None and str(widget_val).strip():
            query_overrides[key] = str(widget_val).strip()
    if query_overrides:
        overrides["query_params"] = query_overrides

    path_overrides = {}
    for key in (default_req.get("path_params") or {}):
        widget_val = st.session_state.get(f"{prefix}_p_{key}")
        if widget_val is not None and str(widget_val).strip():
            path_overrides[key] = str(widget_val).strip()
    if path_overrides:
        overrides["path_params"] = path_overrides

    return overrides

def _rerun_env_values(prefix: str, base_env: dict) -> dict:
    env = dict(base_env or {})
    env["ACCESS_TOKEN"] = str(st.session_state.get(f"{prefix}_token", env.get("ACCESS_TOKEN", "")) or "")
    env["API_KEY"] = str(st.session_state.get(f"{prefix}_apikey", env.get("API_KEY", "")) or "")
    return env

def _results_dataframe(run_results: list[dict]) -> pd.DataFrame:
    rows = []
    for r in run_results:
        if r.get("skipped"):
            badge, got = "⏭ Skipped", "—"
        elif r.get("error"):
            badge, got = "⚠ Error", "ERR"
        elif r.get("passed"):
            badge, got = "✅ Pass", str(r["actual_status"])
        else:
            badge, got = "❌ Fail", str(r["actual_status"])
        rows.append({
            "ID":          r["id"],
            "Category":    r["category"],
            "Description": (r["description"] or "")[:65],
            "Expected":    str(r["expected_status"]) if r["expected_status"] else "—",
            "Got":         got,
            "Assertions":  "; ".join(r.get("assertion_failures") or [])[:40] or "—",
            "Result":      badge,
            "Time (ms)":   r["response_time_ms"] if r["response_time_ms"] else "—",
        })
    return pd.DataFrame(rows)


_RESULT_DETAIL_FILTERS = ("All", "Failed", "Errors", "Passed", "Skipped")


def _result_icon(result: dict) -> str:
    if result.get("skipped"):
        return "⏭"
    if result.get("error"):
        return "⚠"
    if result.get("passed"):
        return "✅"
    return "❌"


def _result_option_label(result: dict) -> str:
    desc = (result.get("description") or "")[:70]
    return f"{_result_icon(result)} {result['id']} — {desc}"


def _filter_run_results(run_results: list[dict], filter_name: str) -> list[dict]:
    if filter_name == "Failed":
        return [
            r for r in run_results
            if not r.get("passed") and not r.get("skipped") and not r.get("error")
        ]
    if filter_name == "Errors":
        return [r for r in run_results if r.get("error")]
    if filter_name == "Passed":
        return [r for r in run_results if r.get("passed")]
    if filter_name == "Skipped":
        return [r for r in run_results if r.get("skipped")]
    return list(run_results)


def _render_single_result_detail(
    result: dict,
    *,
    case_by_id: dict,
    selection_key: str,
    values: dict,
    norm_map: dict,
    run_results: list[dict],
) -> None:
    """Render one test case's response detail and rerun editor."""
    if result.get("skipped"):
        st.caption("Skipped — rate_limit category")
        return

    ca, cb, cc = st.columns(3)
    ca.metric("Expected", result["expected_status"])
    cb.metric("Got", result["actual_status"])
    cc.metric("Time", f"{result['response_time_ms']} ms")
    if result.get("error"):
        st.error(result["error"])
    if result.get("request_url"):
        st.caption("Request URL")
        st.code(result["request_url"], language=None)
    if result.get("request"):
        st.caption("Request sent")
        st.json(result["request"])

    default_req = result.get("request") or {}
    rerun_prefix = f"rerun_{selection_key}_{result.get('id')}"
    base_env = st.session_state.get("runner_env_values", {})

    st.divider()
    st.caption("Edit and rerun with different auth / parameters / payload")

    ra1, ra2 = st.columns(2)
    ra1.text_input(
        "Access token",
        value=str(base_env.get("ACCESS_TOKEN", "") or ""),
        type="password",
        key=f"{rerun_prefix}_token",
    )
    ra2.text_input(
        "API key",
        value=str(base_env.get("API_KEY", "") or ""),
        type="password",
        key=f"{rerun_prefix}_apikey",
    )

    for key, val in (default_req.get("query_params") or {}).items():
        st.text_input(
            f"Query param: {key}",
            value=str(val),
            key=f"{rerun_prefix}_q_{key}",
        )
    for key, val in (default_req.get("path_params") or {}).items():
        st.text_input(
            f"Path param: {key}",
            value=str(val),
            key=f"{rerun_prefix}_p_{key}",
        )

    body_default = ""
    if default_req.get("body") is not None:
        try:
            body_default = json.dumps(default_req.get("body"), indent=2)
        except TypeError:
            body_default = str(default_req.get("body"))
    st.text_area(
        "Request body (JSON or text)",
        value=body_default,
        height=120,
        key=f"{rerun_prefix}_body",
    )
    headers_default = json.dumps(default_req.get("headers") or {}, indent=2)
    st.text_area(
        "Headers (JSON object)",
        value=headers_default,
        height=80,
        key=f"{rerun_prefix}_headers",
    )
    edited_url = st.text_input(
        "Request URL",
        value=result.get("request_url") or "",
        key=f"{rerun_prefix}_url",
    )

    if st.button(
        "↺ Rerun with edits",
        key=f"rerun_case_{selection_key}_{result.get('id')}",
        disabled=not edited_url.strip(),
    ):
        rerun_env = _rerun_env_values(rerun_prefix, base_env)
        req_overrides = _rerun_request_overrides(rerun_prefix, default_req)
        case = case_by_id.get(result.get("id"), {})
        export_norm = st.session_state.get("export_norm_map") or norm_map or {}
        new_result = runner.run_case(
            case,
            base_url=st.session_state.get("runner_base_url", "").strip(),
            user_vals=values,
            env_vals=rerun_env,
            timeout=int(st.session_state.get("runner_timeout_s", 10)),
            url_override=edited_url.strip(),
            max_response_ms=int(st.session_state.get("runner_max_resp_ms", 0) or 0) or None,
            param_overrides=st.session_state.get("request_param_values", {}),
            request_overrides=req_overrides,
            norm_endpoint=(
                ingester.lookup_norm(export_norm, case.get("endpoint", {}))
                if case.get("endpoint")
                else None
            ),
        )
        st.session_state.run_results = [
            new_result if old.get("id") == result.get("id") else old
            for old in run_results
        ]
        st.rerun()

    if result.get("response_body"):
        st.caption("Response body")
        st.code(result["response_body"], language="json")


def _render_result_details_panel(
    run_results: list[dict],
    *,
    raw_cases: dict,
    selection_key: str,
    values: dict,
    norm_map: dict,
) -> None:
    """Show response details for one test case at a time (avoids nested expander blow-up)."""
    case_by_id = {c.get("id"): c for c in raw_cases.get("test_cases", [])}
    filter_key = f"result_detail_filter_{selection_key}"
    case_key = f"result_detail_case_{selection_key}"

    with st.expander("Response details per test case", expanded=False):
        fc1, fc2 = st.columns([1, 3])
        detail_filter = fc1.selectbox(
            "Show",
            _RESULT_DETAIL_FILTERS,
            key=filter_key,
        )
        filtered = _filter_run_results(run_results, detail_filter)
        if not filtered:
            st.info("No test cases match this filter.")
            return

        filtered_ids = [r["id"] for r in filtered]
        by_id = {r["id"]: r for r in filtered}
        if st.session_state.get(case_key) not in filtered_ids:
            st.session_state[case_key] = filtered_ids[0]

        selected_id = fc2.selectbox(
            "Test case",
            options=filtered_ids,
            format_func=lambda cid: _result_option_label(by_id[cid]),
            key=case_key,
        )
        selected = by_id[selected_id]
        st.caption(
            f"Showing **1** of **{len(filtered)}** matching cases "
            f"({len(run_results)} total). Select another case above to inspect it."
        )
        _render_single_result_detail(
            selected,
            case_by_id=case_by_id,
            selection_key=selection_key,
            values=values,
            norm_map=norm_map,
            run_results=run_results,
        )

_colour_results = ui.colour_results
_step = ui.step
_sec = ui.sec


# ══════════════════════════════════════════════════════════════════════════
# INPUT SOURCE
# ══════════════════════════════════════════════════════════════════════════
input_mode = st.radio(
    "Input source",
    ["OpenAPI spec", "Postman collection", "cURL command"],
    horizontal=True,
    key="input_mode",
)

uploaded_file = None
curl_text = ""
import_bundle = None
data = None
input_ready = False

if input_mode == "OpenAPI spec":
    uploaded_file = st.file_uploader(
        "Upload OpenAPI spec",
        type=["json", "yaml", "yml"],
        accept_multiple_files=False,
        key="spec_file_uploader",
        help="JSON or YAML — OpenAPI 3.x or Swagger 2",
    )
    if uploaded_file is not None:
        data = _load_parsed_spec(uploaded_file)
        if isinstance(data, dict) and "error" not in data:
            if data.get("openapi") or data.get("swagger"):
                st.session_state.parsed_spec = data
                st.session_state.input_source = "openapi"
                st.session_state.import_norm_map = None
                input_ready = True
            else:
                st.error("Not an OpenAPI/Swagger spec: missing 'openapi' or 'swagger' version field.")
        elif isinstance(data, dict):
            st.error(data["error"])

elif input_mode == "Postman collection":
    uploaded_file = st.file_uploader(
        "Upload Postman collection",
        type=["json"],
        accept_multiple_files=False,
        key="postman_file_uploader",
        help="Postman Collection v2.1 JSON export",
    )
    if uploaded_file is not None:
        try:
            raw = json.loads(uploaded_file.getvalue().decode("utf-8"))
            import_bundle = postman_importer.parse_collection(raw)
            if import_bundle.get("error"):
                st.error(import_bundle["error"])
            else:
                data = import_bundle["spec"]
                st.session_state.parsed_spec = data
                st.session_state.input_source = "postman"
                st.session_state.import_norm_map = import_bundle.get("norm_map")
                st.session_state.imported_cases = import_bundle.get("imported_cases")
                st.session_state.import_base_url = import_bundle.get("base_url", "")
                input_ready = True
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(f"Invalid JSON: {exc}")

else:
    curl_text = st.text_area(
        "Paste cURL command",
        height=120,
        placeholder="curl -X POST 'https://api.example.com/users' -H 'Authorization: Bearer ...' -d '{\"name\":\"test\"}'",
        key="curl_input_text",
    )
    if curl_text.strip():
        import_bundle = curl_parser.parse_curl(curl_text)
        if import_bundle.get("error"):
            st.error(import_bundle["error"])
        else:
            data = import_bundle["spec"]
            st.session_state.parsed_spec = data
            st.session_state.input_source = "curl"
            st.session_state.import_norm_map = import_bundle.get("norm_map")
            st.session_state.imported_cases = import_bundle.get("imported_cases")
            st.session_state.import_base_url = import_bundle.get("base_url", "")
            input_ready = True

tab_test_gen, tab_docs = st.tabs(["⚒  Test Generator", "📖  API Docs"])


# ══════════════════════════════════════════════════════════════════════════
# TAB 1 — Test Generator
# ══════════════════════════════════════════════════════════════════════════
with tab_test_gen:

    if input_ready and data is not None:
        input_source = st.session_state.get("input_source", "openapi")

        if isinstance(data, dict) and "error" in data:
            st.error(data["error"]); st.stop()
        if not isinstance(data, dict):
            st.error("Parsed content must be a JSON/YAML object."); st.stop()

        api_title   = data.get("info", {}).get("title", "Untitled API")
        api_version = data.get("info", {}).get("version", "")
        if input_source == "openapi":
            n_paths = len(data.get("paths", {}))
            st.success(f"**{api_title}** v{api_version} parsed — {n_paths} path(s) found")
        elif input_source == "postman":
            st.success(f"**{api_title}** — Postman collection imported")
        else:
            st.success(f"**{api_title}** — cURL request imported")

        with st.expander("View raw input"):
            st.json(data)

        if input_source == "openapi":
            endpts = ingester.ListEndpoints(data)
        else:
            if import_bundle:
                endpts = import_bundle.get("endpoints") or []
            else:
                full_norm = st.session_state.get("import_norm_map") or {}
                endpts = [
                    {
                        "method": norm["method"],
                        "path": norm["path"],
                        "summary": norm.get("summary", ""),
                        "operationId": "",
                        "responses": ["200"],
                    }
                    for norm in full_norm.values()
                ]

        # ── STEP 1 ────────────────────────────────────────────────────────
        _step(1, "Select Endpoints")

        if not endpts or "error" in endpts[0]:
            st.warning(endpts[0].get("error", "No endpoints found"))
        else:
            label_counts = {}
            for ep in endpts:
                base = f"{ep['method']} {ep['path']}"
                label_counts[base] = label_counts.get(base, 0) + 1

            ep_labels   = [ingester.endpoint_label(ep, i, label_counts) for i, ep in enumerate(endpts)]
            label_to_ep = dict(zip(ep_labels, endpts))

            selected_labels = st.multiselect(
                "Choose endpoints (1–10)",
                ep_labels,
                max_selections=10,
                help="Select up to 10 endpoints to include in the test suite.",
            )

            if len(selected_labels) > 10:
                st.error("Please select at most 10 endpoints."); st.stop()

            selected_endpts = [label_to_ep[label] for label in selected_labels]
            selection_key   = ingester.selection_key(selected_endpts) if selected_endpts else ""

            if st.session_state.get("cases_selection_key") != selection_key:
                st.session_state.test_cases        = None
                st.session_state.user_input_values = {}
                st.session_state.cases_selection_key = selection_key
                st.session_state.run_results       = None

            norm_map = {}
            if selected_endpts:
                if input_source in ("postman", "curl"):
                    full_norm = st.session_state.get("import_norm_map") or {}
                    norm_map = {
                        ingester.endpoint_key(ep): full_norm[ingester.endpoint_key(ep)]
                        for ep in selected_endpts
                        if ingester.endpoint_key(ep) in full_norm
                    }
                else:
                    norm_map = _load_norm_map(data, selected_endpts, selection_key)
                if not norm_map:
                    st.error("Could not normalize selected endpoints."); st.stop()

                with st.expander(f"LLM payload preview — {len(selected_endpts)} endpoint(s)"):
                    preview = ingester.BuildLLMPayload(data, selected_endpts, norm_map)
                    st.json(preview)

                with st.expander("Spec / imported request bodies"):
                    for ep in selected_endpts:
                        norm = norm_map.get(ingester.endpoint_key(ep))
                        preview_body = spec_bodies.body_summary_for_endpoint(norm)
                        if preview_body:
                            st.markdown(f"**{ep['method']} {ep['path']}**")
                            st.code(preview_body, language="json")
                        else:
                            st.caption(f"{ep['method']} {ep['path']} — no request body")

            # ── STEP 2 ────────────────────────────────────────────────────
            _step(2, "Generate Test Cases")

            if "test_cases" not in st.session_state:
                st.session_state.test_cases = None

            generate_disabled = not selected_endpts or len(selected_labels) == 0
            import_only = False
            if input_source in ("postman", "curl"):
                import_only = st.checkbox(
                    "Use imported requests only (skip LLM generation)",
                    value=False,
                    help="Run the Postman/cURL requests as-is. LLM can still expand coverage when unchecked.",
                )
                if import_only:
                    generate_disabled = False

            provider_col, model_col, depth_col = st.columns([2, 2, 1])
            provider_name = provider_col.selectbox("LLM Provider", get_avl_providers())
            provider      = get_provider(provider_name)

            depth_labels = {
                "Light (10)": 10,
                "Standard (20)": 20,
                "Deep (35)": 35,
                "Max (50)": 50,
            }
            depth_label = depth_col.selectbox(
                "Test depth",
                list(depth_labels.keys()),
                index=1,
                help="Maximum test cases the LLM may generate.",
            )
            max_cases = depth_labels[depth_label]

            if not provider.is_configured():
                st.warning(f"**{provider_name}** is not configured — update your `.env` file.")
                if not import_only:
                    generate_disabled = True

            models = _list_models_cached(provider_name) if provider.is_configured() else []
            if not models and not import_only:
                if provider.is_configured():
                    st.warning(f"No compatible models found for {provider_name}.")
                generate_disabled = True

            chosen_model = None
            if models and not import_only:
                model_options = {f"{display} ({name})": name for name, display in models}
                label         = model_col.selectbox("Model", list(model_options.keys()))
                chosen_model  = model_options[label]
            elif import_only:
                model_col.caption("LLM skipped — import mode")

            gen_label = "✦ Import Test Cases" if import_only else "✦ Generate Test Cases"
            if st.button(
                gen_label,
                disabled=generate_disabled or (not import_only and not chosen_model),
                type="primary",
                use_container_width=True,
            ):
                imported_for_finalize = (
                    st.session_state.get("imported_cases")
                    or (import_bundle.get("imported_cases") if import_bundle else None)
                )
                if import_only:
                    cases = _build_import_only_suite(
                        selected_endpts,
                        imported_for_finalize or [],
                        api_title,
                    )
                    cases = _finalize_test_suite(
                        cases, norm_map, imported_cases=imported_for_finalize
                    )
                else:
                    llm_payload = ingester.BuildLLMPayload(data, selected_endpts, norm_map)
                    with st.spinner(f"Generating up to {max_cases} test cases…"):
                        cases = _generate_test_suite(provider, chosen_model, llm_payload, max_cases)
                    if isinstance(cases, dict) and "error" not in cases:
                        cases = _finalize_test_suite(
                            cases, norm_map, imported_cases=imported_for_finalize
                        )

                if not isinstance(cases, dict):
                    st.error("LLM provider returned an invalid response type.")
                    st.session_state.test_cases = None
                elif "error" not in cases:
                    st.session_state.test_cases          = cases
                    st.session_state.cases_selection_key = selection_key
                    st.session_state.export_norm_map     = norm_map
                    st.session_state.user_input_values   = {}
                    st.session_state.request_param_values = {}
                    st.session_state.generation_target   = max_cases
                    st.session_state.run_results         = None
                    got = len(cases.get("test_cases") or [])
                    if got < max_cases:
                        st.warning(
                            f"Generated **{got}** test cases (target was **{max_cases}**). "
                            "Try **Max (50)** depth or regenerate — the LLM sometimes returns fewer cases."
                        )
                    else:
                        st.success(f"Generated **{got}** test cases.")
                else:
                    st.error(f"Generation failed: {cases.get('error', 'unknown error')}")
                    if cases.get("raw"):
                        with st.expander("Raw LLM output"):
                            st.code(cases["raw"])
                    st.session_state.test_cases = None

            if not selected_labels:
                st.info("Select at least one endpoint above to enable generation.")

            if isinstance(st.session_state.test_cases, dict):
                raw_cases     = st.session_state.test_cases
                catalog       = user_inputs.build_input_catalog(raw_cases)
                widget_prefix = f"ui_{selection_key}"

                if catalog:
                    st.divider()
                    _sec("Test data — fill once, applied across all endpoints")

                    with st.container(border=True):
                        hdr1, hdr2, hdr3 = st.columns([2, 3, 2])
                        hdr1.markdown("**Field**")
                        hdr2.markdown("**Your value**")
                        hdr3.markdown("**Env variable**")

                        for name, meta in sorted(catalog.items()):
                            c1, c2, c3 = st.columns([2, 3, 2])
                            c1.markdown(f"`{name}`")
                            c3.markdown(f"`{meta['env_key']}`")
                            hint = meta.get("hint") or f"Value for {name}"
                            c2.text_input(
                                hint,
                                key=f"{widget_prefix}_{name}",
                                label_visibility="collapsed",
                                placeholder=f"e.g. your real {name}",
                            )
                            if meta.get("cases"):
                                c1.caption("Used in: " + ", ".join(meta["cases"]))

                    values = user_inputs.read_input_values_from_session(catalog, st.session_state, widget_prefix)
                    st.session_state.user_input_values = values

                    missing = user_inputs.unresolved_fields(raw_cases, values)
                    if missing:
                        st.warning("Still required: **" + "**, **".join(missing) + "**")
                    else:
                        st.success("All test data values provided.")
                else:
                    st.session_state.user_input_values = {}

                param_catalog = user_inputs.build_request_params_catalog(raw_cases)
                param_prefix  = f"params_{selection_key}"
                if param_catalog:
                    st.divider()
                    _sec("Request parameters — edit query / path values before running")

                    with st.container(border=True):
                        ph1, ph2, ph3 = st.columns([2, 3, 2])
                        ph1.markdown("**Param**")
                        ph2.markdown("**Your value**")
                        ph3.markdown("**Used in**")

                        for key, meta in sorted(param_catalog.items()):
                            pc1, pc2, pc3 = st.columns([2, 3, 2])
                            loc_label = "Query" if meta["location"] == "query" else "Path"
                            pc1.markdown(f"{loc_label} · `{meta['name']}`")
                            widget_key = f"{param_prefix}_{key}"
                            if widget_key not in st.session_state:
                                st.session_state[widget_key] = meta.get("sample") or ""
                            pc2.text_input(
                                f"Value for {meta['name']}",
                                key=widget_key,
                                label_visibility="collapsed",
                                placeholder=meta.get("sample") or f"e.g. value for {meta['name']}",
                            )
                            if meta.get("cases"):
                                pc3.caption(", ".join(meta["cases"][:4]))

                    param_values = user_inputs.read_param_values_from_session(
                        param_catalog, st.session_state, param_prefix
                    )
                    st.session_state.request_param_values = param_values
                else:
                    st.session_state.request_param_values = {}

                values        = st.session_state.get("user_input_values", {})
                param_values  = st.session_state.get("request_param_values", {})
                missing       = user_inputs.unresolved_fields(raw_cases, values)
                summary_rows  = user_inputs.summarize_test_cases(raw_cases, values)
                num_endpoints = len(raw_cases.get("endpoints") or [])
                gen_target    = st.session_state.get("generation_target", len(summary_rows))

                st.divider()
                col_count, col_ep = st.columns([3, 1])
                col_count.markdown(
                    f"**{len(summary_rows)} / {gen_target} test cases** · {num_endpoints} endpoint(s)"
                )

                coverage = runner.category_coverage(raw_cases)
                if coverage:
                    cov_parts = [f"`{k}`: {v}" for k, v in sorted(coverage.items())]
                    st.caption("Category coverage — " + " · ".join(cov_parts))
                    neg_count = sum(
                        coverage.get(k, 0)
                        for k in (
                            "validation", "boundary", "auth", "optional_fields",
                            "security", "rfc_semantics", "rfc_problem", "rfc_cookies",
                        )
                    )
                    if neg_count == 0:
                        st.warning(
                            "No validation/boundary/security/RFC edge cases found. "
                            "Regenerate with **Deep (35)+** depth, or ensure your spec defines "
                            "parameters/requestBody so edge cases can be auto-generated."
                        )

                # ── Results OR plain summary table ─────────────────────────
                run_res = st.session_state.get("run_results")

                if run_res:
                    s = runner.stats(run_res)
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Total",      s["total"])
                    m2.metric("✅ Passed",  s["passed"])
                    m3.metric("❌ Failed",  s["failed"])
                    m4.metric("⚠ Errors",  s["error"])
                    m5.metric("⏭ Skipped", s["skipped"])

                    df     = _results_dataframe(run_res)
                    styled = _colour_results(df)
                    st.dataframe(styled, use_container_width=True, hide_index=True)

                    _render_result_details_panel(
                        run_res,
                        raw_cases=raw_cases,
                        selection_key=selection_key,
                        values=values,
                        norm_map=norm_map,
                    )

                    report_meta = {
                        "base_url": st.session_state.get("runner_base_url", ""),
                        "api": data.get("info", {}).get("title", ""),
                        "environment": st.session_state.get("active_tier", "DEV"),
                    }
                    html_report = test_report.build_html_report(
                        run_res,
                        suite_name=raw_cases.get("test_suite_name", "API Forge Run"),
                        meta=report_meta,
                        security_scan=st.session_state.get("security_scan"),
                    )
                    json_report = test_report.build_json_report(
                        run_res,
                        suite_name=raw_cases.get("test_suite_name", "API Forge Run"),
                        meta=report_meta,
                    )
                    rp1, rp2 = st.columns(2)
                    rp1.download_button(
                        "⬇  HTML report",
                        html_report,
                        "api_forge_report.html",
                        mime="text/html",
                        use_container_width=True,
                    )
                    rp2.download_button(
                        "⬇  JSON report",
                        json_report,
                        "api_forge_report.json",
                        mime="application/json",
                        use_container_width=True,
                    )

                    if st.button("✕ Clear results", key="clear_results"):
                        st.session_state.run_results = None
                        st.rerun()

                else:
                    st.dataframe(summary_rows, use_container_width=True, hide_index=True)

                # ── STEP 3 ────────────────────────────────────────────────
                _step(3, "Run Tests")

                servers = ingester.ResolveServers(data)
                def_url = (
                    st.session_state.get("import_base_url")
                    or (servers[0].get("url", "") if servers else "")
                )

                with st.container(border=True):
                    runner_norm_map = (
                        st.session_state.get("export_norm_map")
                        or st.session_state.get("_norm_map")
                        or norm_map
                    )
                    env_template = pytest_exporter.CollectEnvVars(runner_norm_map, test_suite=raw_cases, user_values=values)
                    env_template = {
                        k: v for k, v in (env_template or {}).items()
                        if k and str(k).lower() != "none" and str(v).strip().lower() != "none"
                    }

                    env_session_key = selection_key
                    if st.session_state.get("runner_env_key") != env_session_key:
                        init_env = dict(st.session_state.get("runner_env_values") or {})
                        for k, v in (env_template or {}).items():
                            if k not in init_env or not init_env.get(k):
                                s = "" if (isinstance(v, str) and v.startswith("<")) else (v or "")
                                init_env[k] = str(s)
                        if "API_BASE_URL" not in init_env or not init_env.get("API_BASE_URL"):
                            init_env["API_BASE_URL"] = def_url
                        st.session_state.runner_env_key = env_session_key
                        st.session_state.runner_env_values = init_env

                    runner_env = {
                        k: v for k, v in st.session_state.get("runner_env_values", {}).items()
                        if k and str(k).lower() != "none" and str(v).strip().lower() != "none"
                    }

                    runner_env = ui.render_auth_panel(selection_key, runner_env)

                    st.divider()
                    _sec("Environment variables")
                    st.caption("Additional variables from the spec or generated suite.")

                    common_keys = [
                        k for k in ("ACCESS_TOKEN", "API_KEY", "INVALID_TOKEN", "EXPIRED_TOKEN")
                        if k in runner_env or k in (env_template or {})
                    ]
                    extra_keys = sorted(
                        k for k in (env_template or {}).keys()
                        if k not in set(common_keys) and k != "API_BASE_URL"
                    )

                    def _env_input(key: str):
                        val      = str(runner_env.get(key, "") or "")
                        is_secret = any(x in key for x in ("TOKEN", "PASSWORD", "KEY"))
                        if key in ("ACCESS_TOKEN", "API_KEY"):
                            return
                        st.text_input(
                            key, value=val,
                            key=f"runner_env_{selection_key}_{key}",
                            type="password" if is_secret else "default",
                        )
                        runner_env[key] = str(st.session_state.get(f"runner_env_{selection_key}_{key}", "") or "")

                    cols = st.columns(2)
                    with cols[0]:
                        if "INVALID_TOKEN" in (env_template or runner_env): _env_input("INVALID_TOKEN")
                    with cols[1]:
                        if "EXPIRED_TOKEN" in (env_template or runner_env): _env_input("EXPIRED_TOKEN")

                    if extra_keys:
                        with st.expander("More variables"):
                            for k in extra_keys: _env_input(k)

                    st.session_state.runner_env_values = runner_env

                    suite_blob = json.dumps(raw_cases.get("test_cases", []))
                    if "VALID_TOKEN" in suite_blob and not (runner_env.get("ACCESS_TOKEN") or "").strip():
                        st.warning("Suite uses `VALID_TOKEN` but `ACCESS_TOKEN` is empty — those requests will likely get 401.")

                    st.divider()
                    _sec("Run options")

                    all_categories = sorted(
                        {c.get("category") or "unknown" for c in raw_cases.get("test_cases", [])}
                    )
                    run_categories = st.multiselect(
                        "Categories to run (empty = all)",
                        all_categories,
                        default=all_categories,
                        help="Filter which test categories to execute.",
                    )

                    opt1, opt2, opt3 = st.columns(3)
                    max_resp_ms = opt1.number_input(
                        "Max response time (ms, 0 = off)",
                        min_value=0,
                        max_value=60000,
                        value=0,
                        step=100,
                        key="runner_max_resp_ms",
                    )
                    concurrency = opt2.number_input(
                        "Parallel workers",
                        min_value=1,
                        max_value=10,
                        value=5,
                        step=1,
                        key="runner_concurrency",
                    )
                    skip_r1 = opt3.checkbox(
                        "Skip rate_limit tests",
                        value=True,
                        help="Avoids accidentally hammering the server.",
                    )

                    run_security_scan = st.checkbox(
                        "Run security scan after tests",
                        value=True,
                        help="Checks response headers, CORS, cookies, RFC 7807 problem responses.",
                    )

                    st.divider()
                    _sec("Target server")

                    base_url = st.text_input(
                        "Base URL",
                        value=runner_env.get("API_BASE_URL") or def_url,
                        key="runner_base_url",
                        help="The server URL all test requests are sent to.",
                    )
                    runner_env["API_BASE_URL"]              = base_url
                    st.session_state.runner_env_values      = runner_env

                    timeout_s = st.number_input(
                        "Timeout per request (s)",
                        min_value=3,
                        max_value=30,
                        value=10,
                        step=1,
                        key="runner_timeout_s",
                    )

                    run_ok = bool(base_url.strip()) and not missing
                    if not base_url.strip():
                        st.caption("⚠ Enter a Base URL to enable test execution.")
                    elif missing:
                        st.caption("⚠ Fill all required test data fields before running tests.")

                    if st.button("▶  Run Tests", disabled=not run_ok, type="primary", use_container_width=True):
                        n_cases = len(raw_cases.get("test_cases", []))
                        progress = st.progress(0, text="Running tests…")

                        def _progress(done: int, total: int):
                            progress.progress(done / total if total else 1.0, text=f"Running {done}/{total}…")

                        export_norm = (
                            st.session_state.get("export_norm_map")
                            or st.session_state.get("_norm_map")
                            or norm_map
                        )
                        results = runner.run_cases(
                            suite=raw_cases,
                            base_url=base_url.strip(),
                            user_vals=values,
                            env_vals=runner_env,
                            timeout=int(timeout_s),
                            skip_rate_limit=skip_r1,
                            concurrency=int(concurrency),
                            categories_filter=run_categories if run_categories else None,
                            max_response_ms=int(max_resp_ms) if max_resp_ms > 0 else None,
                            norm_map=export_norm,
                            progress_callback=_progress,
                            param_overrides=param_values,
                        )
                        progress.empty()
                        st.session_state.run_results = results
                        if run_security_scan:
                            st.session_state.security_scan = security_scanner.scan_run_results(
                                results, environment="DEV"
                            )
                        else:
                            st.session_state.security_scan = None
                        st.rerun()

                # ── STEP 4 ────────────────────────────────────────────────
                _step(4, "Downloads")

                run_res_dl = st.session_state.get("run_results")
                if run_res_dl:
                    st.divider()
                    _sec("Test reports")
                    report_meta = {
                        "base_url": st.session_state.get("runner_base_url", ""),
                        "api": data.get("info", {}).get("title", ""),
                        "environment": st.session_state.get("active_tier", "DEV"),
                    }
                    html_report = test_report.build_html_report(
                        run_res_dl,
                        suite_name=raw_cases.get("test_suite_name", "API Forge Run"),
                        meta=report_meta,
                        security_scan=st.session_state.get("security_scan"),
                    )
                    json_report = test_report.build_json_report(
                        run_res_dl,
                        suite_name=raw_cases.get("test_suite_name", "API Forge Run"),
                        meta=report_meta,
                    )
                    s = runner.stats(run_res_dl)
                    st.caption(
                        f"Last run — {s['passed']} passed · {s['failed']} failed · "
                        f"{s['error']} errors · {s['skipped']} skipped"
                    )
                    rr1, rr2 = st.columns(2)
                    rr1.download_button(
                        "⬇  HTML report",
                        html_report,
                        "api_forge_report.html",
                        mime="text/html",
                        use_container_width=True,
                        key="download_html_report_step4",
                    )
                    rr2.download_button(
                        "⬇  JSON report",
                        json_report,
                        "api_forge_report.json",
                        mime="application/json",
                        use_container_width=True,
                        key="download_json_report_step4",
                    )

                    sec_scan = st.session_state.get("security_scan")
                    if sec_scan:
                        st.divider()
                        _sec("Security scan")
                        st.caption(sec_scan.get("summary", ""))
                        ss1, ss2 = st.columns(2)
                        ss1.download_button(
                            "⬇  Security scan (HTML)",
                            security_scanner.build_security_report_html(sec_scan),
                            "api_forge_security_report.html",
                            mime="text/html",
                            use_container_width=True,
                            key="download_security_html",
                        )
                        ss2.download_button(
                            "⬇  Security scan (JSON)",
                            security_scanner.build_security_report_json(sec_scan),
                            "api_forge_security_report.json",
                            mime="application/json",
                            use_container_width=True,
                            key="download_security_json",
                        )

                    runner_env = st.session_state.get("runner_env_values", {})
                    profile_export = environment_profiles.export_profile_text(
                        "DEV",
                        {
                            "API_BASE_URL": runner_env.get("API_BASE_URL", ""),
                            "ACCESS_TOKEN": runner_env.get("ACCESS_TOKEN", ""),
                            "API_KEY": runner_env.get("API_KEY", ""),
                        },
                    )
                    st.download_button(
                        "⬇  Export session profile",
                        profile_export,
                        "api_forge_profile.env",
                        mime="text/plain",
                        use_container_width=True,
                        key="download_tier_profile",
                    )

                export_norm_map = (
                    st.session_state.get("export_norm_map")
                    or st.session_state.get("_norm_map")
                    or norm_map
                )
                if not export_norm_map and selected_endpts:
                    export_norm_map = _load_norm_map(data, selected_endpts, selection_key)

                cases_json    = _stable_json(raw_cases)
                norm_map_json = _stable_json(export_norm_map)
                values_json   = _stable_json(values)
                try:
                    display_json, env, pytest_test, postman_json = _temp_exports(cases_json, norm_map_json, values_json)
                except Exception as e:
                    st.error(f"Could not build downloads: {e}"); st.stop()

                with st.expander("View full test suite JSON"):
                    st.json(json.loads(display_json))

                c1, c2, c3, c4 = st.columns(4)
                c1.download_button("⬇  JSON",               display_json,  "cases.json",             mime="application/json", use_container_width=True, icon=":material/download:")
                c2.download_button("⬇  Postman Collection", postman_json,  "postman_collection.json", mime="application/json", use_container_width=True, icon=":material/download:")
                c3.download_button("⬇  Pytest file",        pytest_test,   "test_pytest.py",          mime="text/x-python",    use_container_width=True, icon=":material/download:")
                c4.download_button("⬇  .env template",      env,           "api_forge.env",           mime="text/plain",        use_container_width=True, icon=":material/download:")

                with st.expander(".env template preview"):
                    st.code(env, language="ini")

    else:
        st.info("Choose an input source above — OpenAPI spec, Postman collection, or cURL command.")


# ══════════════════════════════════════════════════════════════════════════
# TAB 2 — API Docs
# ══════════════════════════════════════════════════════════════════════════
with tab_docs:
    spec = st.session_state.get("parsed_spec")
    if spec is None:
        st.info("Upload a spec file in the Test Generator tab to view its documentation here.")
    else:
        api_title   = spec.get("info", {}).get("title",   "API Docs")
        api_version = spec.get("info", {}).get("version", "")
        st.write(f"### {api_title}  `v{api_version}`")
        api_doc_redoc.render_redoc(spec, height=900)
