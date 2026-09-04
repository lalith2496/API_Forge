from llm.base import validate_test_suite


def _minimal_suite():
    return {
        "test_suite_name": "Demo",
        "endpoints": [{"method": "GET", "path": "/items"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "GET", "path": "/items"},
                "category": "happy_path",
                "description": "list items",
                "requires_user_input": False,
                "request": {
                    "method": "GET",
                    "path": "/items",
                    "headers": {},
                    "query_params": {},
                    "path_params": {},
                    "body": None,
                },
                "expected": {
                    "status_code": 200,
                    "response_assertions": ["response is valid JSON"],
                },
            }
        ],
    }


def test_validate_test_suite_accepts_minimal():
    ok, err = validate_test_suite(_minimal_suite())
    assert ok
    assert err is None


def test_validate_test_suite_rejects_missing_happy_path():
    suite = _minimal_suite()
    suite["test_cases"][0]["category"] = "validation"
    ok, err = validate_test_suite(suite)
    assert not ok
    assert "happy_path" in err


def test_validate_test_suite_rejects_bad_assertions_type():
    suite = _minimal_suite()
    suite["test_cases"][0]["expected"]["response_assertions"] = "not-a-list"
    ok, err = validate_test_suite(suite)
    assert not ok
    assert "response_assertions" in err


def test_validate_test_suite_accepts_structured_assertions():
    suite = _minimal_suite()
    suite["test_cases"][0]["expected"]["response_assertions"] = [
        "response is valid JSON",
        {"type": "jsonpath_exists", "path": "$.id"},
    ]
    ok, err = validate_test_suite(suite)
    assert ok
    assert err is None
