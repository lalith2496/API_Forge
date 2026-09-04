import case_normalizer
import spec_bodies


def test_null_body_happy_path_becomes_validation_400():
    suite = {
        "test_suite_name": "API",
        "endpoints": [{"method": "POST", "path": "/articles"}],
        "test_cases": [{
            "id": "TC-01",
            "endpoint": {"method": "POST", "path": "/articles"},
            "category": "happy_path",
            "description": "Create article with null request body payload",
            "request": {
                "method": "POST",
                "path": "/articles",
                "headers": {},
                "query_params": {},
                "path_params": {},
                "body": None,
            },
            "expected": {"status_code": 200, "response_assertions": []},
        }],
    }
    norm_map = {
        "POST:/articles": {
            "method": "POST",
            "path": "/articles",
            "parameters": [],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"example": {"title": "Hi"}}},
            },
            "responses": {"201": {}, "400": {}},
        }
    }
    out = case_normalizer.normalize_generated_cases(suite, norm_map)
    case = out["test_cases"][0]
    assert case["category"] == "validation"
    assert case["expected"]["status_code"] == 400


def test_extra_query_param_happy_path_becomes_validation_400():
    suite = {
        "test_suite_name": "API",
        "endpoints": [{"method": "GET", "path": "/articles"}],
        "test_cases": [{
            "id": "TC-01",
            "endpoint": {"method": "GET", "path": "/articles"},
            "category": "happy_path",
            "description": "GET with unsupported query parameters",
            "request": {
                "method": "GET",
                "path": "/articles",
                "headers": {},
                "query_params": {"contentIds": "1", "foo": "bar"},
                "path_params": {},
                "body": None,
            },
            "expected": {"status_code": 200, "response_assertions": []},
        }],
    }
    norm_map = {
        "GET:/articles": {
            "method": "GET",
            "path": "/articles",
            "parameters": [
                {"name": "contentIds", "in": "query", "schema": {"type": "string"}, "example": "1"},
            ],
            "responses": {"200": {}, "400": {}},
        }
    }
    out = case_normalizer.normalize_generated_cases(suite, norm_map)
    case = out["test_cases"][0]
    assert case["category"] == "validation"
    assert case["expected"]["status_code"] == 400
    assert out["test_cases"][0]["request"]["query_params"]["foo"] == "bar"


def test_only_one_happy_path_per_endpoint():
    suite = {
        "test_suite_name": "API",
        "endpoints": [{"method": "POST", "path": "/articles"}],
        "test_cases": [
            {
                "id": "TC-01",
                "endpoint": {"method": "POST", "path": "/articles"},
                "category": "happy_path",
                "description": "canonical create",
                "request": {
                    "method": "POST", "path": "/articles",
                    "headers": {}, "query_params": {}, "path_params": {},
                    "body": {"title": "Hi"},
                },
                "expected": {"status_code": 201},
            },
            {
                "id": "TC-02",
                "endpoint": {"method": "POST", "path": "/articles"},
                "category": "happy_path",
                "description": "create with valid Authorization header",
                "request": {
                    "method": "POST", "path": "/articles",
                    "headers": {"Authorization": "Bearer x"},
                    "query_params": {}, "path_params": {},
                    "body": {"title": "Hi"},
                },
                "expected": {"status_code": 201},
            },
        ],
    }
    norm_map = {
        "POST:/articles": {
            "method": "POST",
            "path": "/articles",
            "parameters": [],
            "requestBody": {
                "required": True,
                "content": {"application/json": {"example": {"title": "Hi"}}},
            },
            "responses": {"201": {}},
        }
    }
    out = case_normalizer.normalize_generated_cases(suite, norm_map)
    happy = [c for c in out["test_cases"] if c["category"] == "happy_path"]
    assert len(happy) == 1
    assert happy[0]["id"] == "TC-01"


def test_optional_fields_becomes_validation_400():
    suite = {
        "test_suite_name": "API",
        "endpoints": [{"method": "GET", "path": "/articles"}],
        "test_cases": [{
            "id": "TC-21",
            "endpoint": {"method": "GET", "path": "/articles"},
            "category": "optional_fields",
            "description": "GET article with unsupported query parameters",
            "request": {
                "method": "GET",
                "path": "/articles",
                "query_params": {"contentIds": "1", "unknown": "x"},
                "path_params": {},
                "headers": {},
                "body": None,
            },
            "expected": {"status_code": 400},
        }],
    }
    norm_map = {
        "GET:/articles": {
            "method": "GET",
            "path": "/articles",
            "parameters": [
                {"name": "contentIds", "in": "query", "schema": {"type": "string"}},
            ],
            "responses": {"400": {}},
        }
    }
    out = spec_bodies.enforce_spec_deviation_expectations(suite, norm_map)
    assert out["test_cases"][0]["category"] == "validation"
    assert out["test_cases"][0]["expected"]["status_code"] == 400
