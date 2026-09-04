from parameter_discovery import _merge_imported_request_body
import canonical_templates


def test_merge_imported_body_into_post_norm():
    norm = {
        "method": "POST",
        "path": "/articles",
        "parameters": [],
    }
    imported = [{
        "endpoint": {"method": "POST", "path": "/articles"},
        "request": {
            "headers": {"Content-Type": "application/json"},
            "body": {"title": "Hello", "content": "World"},
        },
    }]
    out = _merge_imported_request_body(norm, {"method": "POST", "path": "/articles"}, imported)
    body, _, _, _ = canonical_templates.build_reference_body(out)
    assert body == {"title": "Hello", "content": "World"}
