import ingester
import parameter_discovery
from streamlit_app import _finalize_test_suite


def test_lookup_norm_without_operation_id():
    norm_map = {
        "GET:/articles:getArticles": {
            "method": "GET",
            "path": "/articles",
            "parameters": [],
            "responses": {"400": {}},
        }
    }
    ep = {"method": "GET", "path": "/articles"}
    assert ingester.lookup_norm(norm_map, ep) is not None


def test_finalize_adds_invalid_value_cases_with_key_mismatch():
    suite = {
        "test_suite_name": "KB",
        "endpoints": [{"method": "GET", "path": "/articles"}],
        "test_cases": [{
            "id": "TC-01",
            "endpoint": {"method": "GET", "path": "/articles"},
            "category": "happy_path",
            "description": "happy",
            "request": {
                "method": "GET",
                "path": "/articles",
                "headers": {},
                "query_params": {"contentIds": "abc-123"},
                "path_params": {},
                "body": None,
            },
            "expected": {"status_code": 200, "response_assertions": []},
        }],
    }
    norm_map = {
        "GET:/articles:getArticles": {
            "method": "GET",
            "path": "/articles",
            "parameters": [],
            "responses": {"200": {}, "400": {}},
        }
    }
    out = _finalize_test_suite(suite, norm_map)
    invalid_cases = [
        c for c in out["test_cases"]
        if c["expected"]["status_code"] == 400
        and c["category"] in ("validation", "security", "boundary")
    ]
    assert len(invalid_cases) >= 2
    assert any("contentIds" in c["description"] for c in invalid_cases)


def test_discover_parameters_from_happy_path():
    norm = {"method": "GET", "path": "/articles", "parameters": []}
    suite = {
        "test_cases": [{
            "endpoint": {"method": "GET", "path": "/articles"},
            "request": {"query_params": {"contentIds": "x", "locale": "en"}},
        }]
    }
    params = parameter_discovery.discover_parameters(
        norm, suite, {"method": "GET", "path": "/articles"}, imported_cases=None
    )
    names = {p["name"] for p in params}
    assert "contentIds" in names
    assert "locale" in names
