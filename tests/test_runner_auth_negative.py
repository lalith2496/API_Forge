import auth_helpers
import runner


def test_runner_preserves_empty_authorization_header():
    case = {
        "id": "TC-06",
        "category": "validation",
        "description": "Attempt GET task with empty Authorization header value",
        "endpoint": {"method": "GET", "path": "/api/v3/task/"},
        "request": {
            "method": "GET",
            "path": "/api/v3/task/",
            "headers": {"Authorization": ""},
            "query_params": {},
            "path_params": {},
            "body": None,
        },
        "expected": {"status_code": 401},
    }
    headers = runner._replace_headers(
        case["request"]["headers"],
        {},
        {"ACCESS_TOKEN": "secret-token", "API_KEY": "api-key"},
        case=case,
    )
    assert headers["Authorization"] == ""

    headers = auth_helpers.apply_auth_headers(headers, case, {"ACCESS_TOKEN": "secret-token"})
    assert headers.get("Authorization", "") == ""
