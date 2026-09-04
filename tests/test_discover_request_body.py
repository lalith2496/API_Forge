import canonical_templates
import parameter_discovery
import spec_bodies


def test_discover_request_body_from_happy_path_case():
    suite = {
        "test_cases": [{
            "category": "happy_path",
            "endpoint": {"method": "POST", "path": "/articles"},
            "request": {
                "headers": {"Content-Type": "application/json"},
                "body": {"title": "From suite", "content": "Body"},
            },
        }],
    }
    body, content_type = parameter_discovery.discover_request_body(
        suite, {"method": "POST", "path": "/articles"}
    )
    assert body == {"title": "From suite", "content": "Body"}
    assert content_type == "application/json"


def test_build_effective_norm_map_attaches_discovered_body():
    norm_map = {
        "POST:/articles": {
            "method": "POST",
            "path": "/articles",
            "parameters": [],
        }
    }
    suite = {
        "endpoints": [{"method": "POST", "path": "/articles"}],
        "test_cases": [{
            "category": "happy_path",
            "endpoint": {"method": "POST", "path": "/articles"},
            "request": {
                "headers": {"Content-Type": "application/json"},
                "body": {"title": "Hello", "content": "World"},
            },
        }],
    }
    effective = parameter_discovery.build_effective_norm_map(suite, norm_map)
    body, _, _, _ = canonical_templates.build_reference_body(effective["POST:/articles"])
    assert body == {"title": "Hello", "content": "World"}


def test_inject_spec_bodies_uses_discovered_body_when_spec_omits_request_body():
    suite = {
        "test_suite_name": "t",
        "endpoints": [{"method": "POST", "path": "/articles"}],
        "test_cases": [
            {
                "id": "TC-01",
                "category": "happy_path",
                "endpoint": {"method": "POST", "path": "/articles"},
                "request": {
                    "method": "POST",
                    "path": "/articles",
                    "headers": {},
                    "body": {"title": "Hello", "content": "World"},
                },
                "expected": {"status_code": 201},
            }
        ],
    }
    norm_map = parameter_discovery.build_effective_norm_map(
        suite,
        {"POST:/articles": {"method": "POST", "path": "/articles", "parameters": []}},
    )
    out = spec_bodies.inject_spec_bodies(suite, norm_map)
    assert out["test_cases"][0]["request"]["body"] == {"title": "Hello", "content": "World"}
