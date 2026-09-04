import invalid_payload_cases
import negative_generator


def test_supplement_invalid_payload_expects_400():
    suite = {
        "test_suite_name": "API",
        "endpoints": [{"method": "POST", "path": "/users"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "POST", "path": "/users"},
                "category": "happy_path",
                "description": "create user",
                "request": {
                    "method": "POST",
                    "path": "/users",
                    "headers": {"Content-Type": "application/json"},
                    "query_params": {},
                    "path_params": {},
                    "body": {"name": "Alice", "email": "a@b.com"},
                },
                "expected": {"status_code": 201, "response_assertions": []},
            }
        ],
    }
    norm_map = {
        "POST:/users": {
            "method": "POST",
            "path": "/users",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["name", "email"],
                            "properties": {
                                "name": {"type": "string"},
                                "email": {"type": "string", "format": "email"},
                            },
                        },
                    }
                },
            },
            "responses": {"400": {"description": "bad request"}},
        }
    }
    out = invalid_payload_cases.supplement_invalid_payload_cases(
        suite, norm_map, negative_generator._base_request
    )
    payload_cases = [
        c for c in out["test_cases"]
        if "invalid_payload:" in (c.get("notes") or "")
    ]
    assert payload_cases
    assert all(c["expected"]["status_code"] == 400 for c in payload_cases)
    assert any("missing required field" in c["description"].lower() for c in payload_cases)
    assert any("wrong type" in c["description"].lower() for c in payload_cases)
