import negative_generator


def _norm_with_query():
    return {
        "method": "GET",
        "path": "/items",
        "parameters": [
            {
                "name": "status",
                "in": "query",
                "required": True,
                "schema": {"type": "string", "enum": ["active", "done"]},
            }
        ],
        "responses": {"400": {"description": "bad request"}},
        "security": [{"type": "http", "scheme": "bearer"}],
    }


def test_supplement_adds_validation_and_auth_cases():
    suite = {
        "test_suite_name": "Demo",
        "endpoints": [{"method": "GET", "path": "/items"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "GET", "path": "/items"},
                "category": "happy_path",
                "description": "ok",
                "request": {
                    "method": "GET",
                    "path": "/items",
                    "headers": {},
                    "query_params": {"status": "active"},
                    "path_params": {},
                    "body": None,
                },
                "expected": {"status_code": 200, "response_assertions": []},
            }
        ],
    }
    norm_map = {"GET:/items": _norm_with_query()}
    out = negative_generator.supplement_negative_cases(suite, norm_map)
    categories = {c["category"] for c in out["test_cases"]}
    assert "validation" in categories or "boundary" in categories
    assert "auth" in categories
    assert len(out["test_cases"]) > 1
