import assertion_sanitizer
import assertions
import parameter_discovery
import spec_bodies


def test_vague_article_assertion_no_longer_treated_as_field():
    ok, msg = assertions.evaluate_assertion(
        "Response contains article data.",
        '{"items": [{"id": "1"}]}',
    )
    assert ok
    assert "field 'article' not found" not in msg


def test_sanitize_drops_hallucinated_field_assertion():
    suite = {
        "test_suite_name": "KB",
        "endpoints": [{"method": "GET", "path": "/articles"}],
        "test_cases": [{
            "id": "TC-01",
            "endpoint": {"method": "GET", "path": "/articles"},
            "category": "happy_path",
            "expected": {
                "status_code": 200,
                "response_assertions": [
                    "Response contains article data.",
                    "response is valid JSON",
                ],
            },
        }],
    }
    norm_map = {
        "GET:/articles": {
            "method": "GET",
            "path": "/articles",
            "responses": {"200": {"description": "ok"}},
        }
    }
    out = assertion_sanitizer.sanitize_response_assertions(suite, norm_map)
    assertions_out = out["test_cases"][0]["expected"]["response_assertions"]
    assert "Response contains article data." not in assertions_out
    assert "response is valid JSON" in assertions_out


def test_post_happy_path_does_not_add_undocumented_query_params():
    suite = {
        "test_suite_name": "API",
        "endpoints": [{"method": "POST", "path": "/articles"}],
        "test_cases": [{
            "id": "TC-01",
            "endpoint": {"method": "POST", "path": "/articles"},
            "category": "happy_path",
            "request": {
                "method": "POST",
                "path": "/articles",
                "headers": {"Content-Type": "application/json"},
                "query_params": {"locale": "en-US", "version": "2"},
                "path_params": {},
                "body": {"title": "Hello"},
            },
            "expected": {"status_code": 201},
        }],
    }
    norm_map = {
        "POST:/articles": {
            "method": "POST",
            "path": "/articles",
            "parameters": [],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": {"title": "Hello"},
                    }
                },
            },
            "responses": {"201": {}},
        }
    }
    imported_cases = [{
        "endpoint": {"method": "POST", "path": "/articles"},
        "request": {
            "query_params": {"locale": "en-US", "version": "2"},
            "path_params": {},
            "body": {"title": "Hello"},
        },
    }]
    from parameter_discovery import build_effective_norm_map

    effective = build_effective_norm_map(suite, norm_map, imported_cases=imported_cases)
    out = spec_bodies.inject_spec_bodies(suite, effective)
    assert out["test_cases"][0]["request"]["query_params"] == {}
    assert len(parameter_discovery.testing_parameters(effective["POST:/articles"])) >= 2
