import security_generator


def test_supplement_adds_security_cases():
    suite = {
        "test_suite_name": "Demo",
        "endpoints": [{"method": "POST", "path": "/users"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "POST", "path": "/users"},
                "category": "happy_path",
                "description": "create",
                "request": {
                    "method": "POST",
                    "path": "/users",
                    "headers": {},
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
            "responses": {"400": {"description": "bad"}},
        }
    }
    out = security_generator.supplement_security_cases(suite, norm_map)
    categories = {c["category"] for c in out["test_cases"]}
    assert "security" in categories
    assert len(out["test_cases"]) > 1
