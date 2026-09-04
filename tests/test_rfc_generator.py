import rfc_generator


def test_supplement_rfc_cases():
    suite = {
        "test_suite_name": "Demo",
        "endpoints": [{"method": "GET", "path": "/items"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "GET", "path": "/items"},
                "category": "happy_path",
                "description": "list",
                "request": {
                    "method": "GET",
                    "path": "/items",
                    "headers": {},
                    "query_params": {},
                    "path_params": {},
                    "body": None,
                },
                "expected": {"status_code": 200, "response_assertions": []},
            }
        ],
    }
    norm_map = {
        "GET:/items": {
            "method": "GET",
            "path": "/items",
            "responses": {"405": {"description": "method not allowed"}, "406": {"description": "not acceptable"}},
        }
    }
    out = rfc_generator.supplement_rfc_cases(suite, norm_map)
    cats = {c["category"] for c in out["test_cases"]}
    assert "rfc_semantics" in cats
