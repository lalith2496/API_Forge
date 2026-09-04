import invalid_value_cases
import negative_generator


def test_supplement_invalid_value_cases_for_get_content_ids():
    suite = {
        "test_suite_name": "KB",
        "endpoints": [{"method": "GET", "path": "/articles"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "GET", "path": "/articles"},
                "category": "happy_path",
                "description": "valid retrieval",
                "request": {
                    "method": "GET",
                    "path": "/articles",
                    "headers": {},
                    "query_params": {"contentIds": "valid-123"},
                    "path_params": {},
                    "body": None,
                },
                "expected": {"status_code": 200, "response_assertions": []},
            }
        ],
    }
    norm_map = {
        "GET:/articles": {
            "method": "GET",
            "path": "/articles",
            "parameters": [
                {
                    "name": "contentIds",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                    "example": "valid-123",
                }
            ],
            "responses": {"400": {"description": "bad request"}},
        }
    }
    out = invalid_value_cases.supplement_invalid_value_cases(
        suite, norm_map, negative_generator._base_request
    )
    value_cases = [
        c for c in out["test_cases"]
        if "invalid_value:" in (c.get("notes") or "")
    ]
    assert value_cases
    assert all(c["expected"]["status_code"] == 400 for c in value_cases)
    assert any("contentIds" in c["description"] for c in value_cases)
    assert any("invalid" in c["description"].lower() for c in value_cases)
