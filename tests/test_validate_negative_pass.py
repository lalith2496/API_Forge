from llm.base import validate_test_suite


def test_validate_allows_negative_only_pass():
    suite = {
        "test_suite_name": "Negative pass",
        "endpoints": [{"method": "GET", "path": "/items"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "GET", "path": "/items"},
                "category": "validation",
                "description": "missing param",
                "requires_user_input": False,
                "request": {
                    "method": "GET",
                    "path": "/items",
                    "headers": {},
                    "query_params": {},
                    "path_params": {},
                    "body": None,
                },
                "expected": {"status_code": 400, "response_assertions": []},
            }
        ],
    }
    ok, err = validate_test_suite(suite, require_happy_path=False)
    assert ok
    assert err is None

    ok_strict, err_strict = validate_test_suite(suite, require_happy_path=True)
    assert not ok_strict
    assert "happy_path" in err_strict
