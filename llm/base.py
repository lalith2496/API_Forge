"""
The base script for calling and integrating LLM models in the app

Now every provider should expose these 3 methods:
    is_configured()
    list_models()
    generate_result(model, prompt)
"""

from abc import ABC, abstractmethod


def _suite_endpoints(data):
    """Normalize legacy single endpoint or multi-endpoint suite."""
    if isinstance(data.get("endpoints"), list) and data["endpoints"]:
        return data["endpoints"]
    ep = data.get("endpoint")
    if isinstance(ep, dict):
        return [ep]
    return []


def _endpoint_tuple(ep):
    return (str(ep.get("method", "")).upper(), str(ep.get("path", "")))


def validate_test_suite(data, require_happy_path: bool = True):
    """
    Validate LLM output shape before exporters consume it.
    Returns (ok: bool, error_message: str | None).

    require_happy_path: set False for negative-only LLM passes that merge later.
    """
    if not isinstance(data, dict):
        return False, "Response is not a JSON object"

    if "error" in data:
        return False, data.get("error", "Unknown error")

    for field in ("test_suite_name", "test_cases"):
        if field not in data:
            return False, f"Missing required field: {field}"

    endpoints = _suite_endpoints(data)
    if not endpoints:
        return False, "Missing endpoints array (or legacy endpoint object)"

    declared = {_endpoint_tuple(ep) for ep in endpoints}
    for i, ep in enumerate(endpoints):
        if not isinstance(ep, dict):
            return False, f"endpoints[{i}] must be an object"
        for field in ("method", "path"):
            if field not in ep or not isinstance(ep[field], str):
                return False, f"endpoints[{i}].{field} must be a non-empty string"

    test_cases = data["test_cases"]
    if not isinstance(test_cases, list) or len(test_cases) == 0:
        return False, "test_cases must be a non-empty array"

    seen_ids = set()
    endpoints_with_happy = set()

    for i, case in enumerate(test_cases):
        if not isinstance(case, dict):
            return False, f"test_cases[{i}] must be an object"

        case_id = case.get("id")
        if not case_id or not isinstance(case_id, str):
            return False, f"test_cases[{i}] missing string 'id'"
        if case_id in seen_ids:
            return False, f"Duplicate test case id: {case_id}"
        seen_ids.add(case_id)

        case_ep = case.get("endpoint")
        if not isinstance(case_ep, dict):
            return False, f"test_cases[{i}].endpoint must be an object"
        ep_t = _endpoint_tuple(case_ep)
        if ep_t not in declared:
            return False, (
                f"test_cases[{i}].endpoint {case_ep} not in declared endpoints"
            )

        if case.get("category") == "happy_path":
            endpoints_with_happy.add(ep_t)

        req = case.get("request")
        if not isinstance(req, dict):
            return False, f"test_cases[{i}].request must be an object"
        for field in ("method", "path"):
            if field not in req:
                return False, f"test_cases[{i}].request missing '{field}'"

        expected = case.get("expected")
        if not isinstance(expected, dict):
            return False, f"test_cases[{i}].expected must be an object"
        if "status_code" not in expected:
            return False, f"test_cases[{i}].expected missing 'status_code'"
        if not isinstance(expected["status_code"], int):
            return False, f"test_cases[{i}].expected.status_code must be an integer"

        assertions = expected.get("response_assertions", [])
        if assertions is not None and not isinstance(assertions, list):
            return False, f"test_cases[{i}].expected.response_assertions must be an array"
        for j, assertion in enumerate(assertions or []):
            if isinstance(assertion, str):
                continue
            if isinstance(assertion, dict):
                if not assertion.get("type"):
                    return False, f"test_cases[{i}].response_assertions[{j}] missing type"
                continue
            return False, f"test_cases[{i}].response_assertions[{j}] must be string or object"

        if "requires_user_input" in case and not isinstance(
            case["requires_user_input"], bool
        ):
            return False, f"test_cases[{i}].requires_user_input must be a boolean"

        user_inputs = case.get("user_inputs")
        if user_inputs is not None and not isinstance(user_inputs, dict):
            return False, f"test_cases[{i}].user_inputs must be an object"

    if require_happy_path:
        missing_happy = declared - endpoints_with_happy
        if missing_happy:
            labels = [f"{m} {p}" for m, p in sorted(missing_happy)]
            return False, f"Missing happy_path for endpoint(s): {', '.join(labels)}"

    return True, None


class LLMProvider(ABC):
    @abstractmethod
    def is_configured(self) -> bool:
        pass
    
    # returns as [[model name, model dispaly hame]]
    @abstractmethod
    def list_models(self) -> list[list[str]]:
        pass

    @abstractmethod
    def generate_result(self, model: str, prompt: str, require_happy_path: bool = True) -> dict:
        pass
