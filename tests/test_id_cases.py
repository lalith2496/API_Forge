import id_cases
import negative_generator


def test_is_id_like_param_content_ids():
    assert id_cases.is_id_like_param("contentIds")
    assert id_cases.is_id_like_param("contentId")
    assert id_cases.is_id_like_param("article_id")
    assert not id_cases.is_id_like_param("status")


def test_supplement_invalid_id_cases_adds_validation_and_security():
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
                }
            ],
            "responses": {"404": {"description": "not found"}, "400": {"description": "bad"}},
        }
    }
    out = id_cases.supplement_invalid_id_cases(suite, norm_map, negative_generator._base_request)
    categories = [c["category"] for c in out["test_cases"]]
    descriptions = " ".join(c["description"] for c in out["test_cases"]).lower()
    assert "validation" in categories
    assert "security" in categories
    assert "invalid" in descriptions or "non-existent" in descriptions or "broken" in descriptions
