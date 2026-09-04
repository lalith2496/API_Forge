import runner
import user_inputs


def test_validation_case_keeps_invalid_content_id_at_runtime():
    case = {
        "id": "TC-20",
        "category": "validation",
        "description": "Invalid contentIds",
        "endpoint": {"method": "GET", "path": "/articles"},
        "request": {
            "method": "GET",
            "path": "/articles",
            "headers": {},
            "query_params": {"contentIds": "not-a-valid-id"},
            "path_params": {},
            "body": None,
        },
        "expected": {"status_code": 400, "response_assertions": []},
    }
    req = user_inputs.apply_request_param_overrides(
        case["request"],
        {"query:contentIds": "6a1e87f5259e22bdc9eb255b"},
        case_category="validation",
    )
    assert req["query_params"]["contentIds"] == "not-a-valid-id"


def test_auth_401_without_json_assertion_passes_status_only():
    from assertion_sanitizer import sanitize_response_assertions

    suite = {
        "test_cases": [{
            "id": "TC-03",
            "category": "auth",
            "endpoint": {"method": "POST", "path": "/articles"},
            "expected": {
                "status_code": 401,
                "response_assertions": ["response is valid JSON"],
            },
        }],
    }
    out = sanitize_response_assertions(suite, {"POST:/articles": {}})
    assert out["test_cases"][0]["expected"]["response_assertions"] == []
