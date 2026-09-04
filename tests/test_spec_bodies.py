import canonical_templates
import spec_bodies


def test_example_from_schema_object():
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
    }
    body = spec_bodies.example_from_schema(schema)
    assert body["name"] == "string"
    assert body["age"] == 1


def test_inject_spec_bodies_fills_missing_body():
    norm_map = {
        "POST:/users": {
            "method": "POST",
            "path": "/users",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {"name": "Alice"},
                    }
                },
            },
        }
    }
    suite = {
        "test_suite_name": "t",
        "endpoints": [{"method": "POST", "path": "/users"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "POST", "path": "/users"},
                "category": "happy_path",
                "request": {"method": "POST", "path": "/users", "headers": {}, "body": None},
                "expected": {"status_code": 201},
            }
        ],
    }
    out = spec_bodies.inject_spec_bodies(suite, norm_map)
    assert out["test_cases"][0]["request"]["body"] == {"name": "Alice"}
    assert out["test_cases"][0]["request"]["headers"]["Content-Type"] == "application/json"


def test_inject_skips_validation_with_bad_body():
    norm_map = {
        "POST:/users": {
            "method": "POST",
            "path": "/users",
            "requestBody": {
                "required": True,
                "content": {"application/json": {"example": {"name": "Alice"}}},
            },
        }
    }
    suite = {
        "test_suite_name": "t",
        "endpoints": [{"method": "POST", "path": "/users"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "POST", "path": "/users"},
                "category": "validation",
                "request": {"method": "POST", "path": "/users", "body": {"name": ""}},
                "expected": {"status_code": 400},
            }
        ],
    }
    out = spec_bodies.inject_spec_bodies(suite, norm_map)
    assert out["test_cases"][0]["request"]["body"] == {"name": ""}


def test_inject_skips_validation_with_empty_body():
    norm_map = {
        "POST:/users": {
            "method": "POST",
            "path": "/users",
            "requestBody": {
                "required": True,
                "content": {"application/json": {"example": {"name": "Alice", "email": "a@b.com"}}},
            },
        }
    }
    suite = {
        "test_suite_name": "t",
        "endpoints": [{"method": "POST", "path": "/users"}],
        "test_cases": [
            {
                "id": "TC-10",
                "endpoint": {"method": "POST", "path": "/users"},
                "category": "validation",
                "description": "Fail to create a user with an empty body",
                "request": {"method": "POST", "path": "/users", "body": {}},
                "expected": {"status_code": 400},
            }
        ],
    }
    out = spec_bodies.inject_spec_bodies(suite, norm_map)
    assert out["test_cases"][0]["request"]["body"] == {}


def test_reference_body_uses_exact_example_without_schema_padding():
    norm = {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "example": {"name": "Alice"},
                    "schema": {
                        "type": "object",
                        "required": ["name", "email"],
                        "properties": {
                            "name": {"type": "string"},
                            "email": {"type": "string"},
                        },
                    },
                }
            },
        }
    }
    reference, _, _, _ = canonical_templates.build_reference_body(norm)
    canonical, _, _, _ = canonical_templates.build_canonical_body(norm)
    assert reference == {"name": "Alice"}
    assert "email" in canonical


def test_enforce_payload_expectations():
    norm_map = {
        "POST:/users": {
            "method": "POST",
            "path": "/users",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {"name": "Alice"},
                        "schema": {
                            "type": "object",
                            "required": ["name", "email"],
                            "properties": {
                                "name": {"type": "string"},
                                "email": {"type": "string"},
                            },
                        },
                    }
                },
            },
        }
    }
    suite = {
        "test_suite_name": "t",
        "endpoints": [{"method": "POST", "path": "/users"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "POST", "path": "/users"},
                "category": "happy_path",
                "request": {
                    "method": "POST",
                    "path": "/users",
                    "headers": {},
                    "body": {"name": "Alice", "email": "extra@example.com", "extra": "field"},
                },
                "expected": {"status_code": 201},
            },
            {
                "id": "TC-02",
                "endpoint": {"method": "POST", "path": "/users"},
                "category": "validation",
                "request": {
                    "method": "POST",
                    "path": "/users",
                    "headers": {},
                    "body": {"name": ""},
                },
                "expected": {"status_code": 422},
            },
        ],
    }
    out = spec_bodies.enforce_payload_expectations(suite, norm_map)
    happy = out["test_cases"][0]
    negative = out["test_cases"][1]
    assert happy["request"]["body"] == {"name": "Alice"}
    assert negative["expected"]["status_code"] == 400
    assert negative["request"]["body"] == {"name": ""}
