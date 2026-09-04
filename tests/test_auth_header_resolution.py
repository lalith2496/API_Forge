import auth_helpers


def test_build_reference_auth_headers_bearer_and_api_key():
    norm = {
        "security": [
            {"type": "http", "scheme": "bearer"},
            {"type": "apiKey", "in": "header", "parameterName": "Key"},
        ],
    }
    headers = auth_helpers.build_reference_auth_headers(norm)
    assert headers["Authorization"] == "Bearer VALID_TOKEN"
    assert headers["Key"] == "API_KEY"


def test_inject_spec_auth_headers_replaces_llm_duplicated_token():
    import ingester

    norm_map = {
        "POST:/articles": {
            "method": "POST",
            "path": "/articles",
            "security": [
                {"type": "http", "scheme": "bearer"},
                {"type": "apiKey", "in": "header", "parameterName": "Key"},
            ],
        }
    }
    suite = {
        "endpoints": [{"method": "POST", "path": "/articles"}],
        "test_cases": [{
            "id": "TC-01",
            "category": "happy_path",
            "endpoint": {"method": "POST", "path": "/articles"},
            "request": {
                "headers": {
                    "Authorization": "Bearer VALID_TOKEN",
                    "Key": "Bearer VALID_TOKEN",
                },
            },
        }],
    }
    out = auth_helpers.inject_spec_auth_headers(suite, norm_map)
    headers = out["test_cases"][0]["request"]["headers"]
    assert headers["Authorization"] == "Bearer VALID_TOKEN"
    assert headers["Key"] == "API_KEY"


def test_resolve_header_value_splits_credentials():
    env = {
        "ACCESS_TOKEN": "Bearer access-token",
        "API_KEY": "api-key-value",
    }
    auth = auth_helpers.resolve_header_value("Authorization", "Bearer VALID_TOKEN", env)
    key = auth_helpers.resolve_header_value("Key", "API_KEY", env)
    assert auth == "Bearer access-token"
    assert key == "api-key-value"


def test_resolve_header_value_strips_bearer_from_key_header():
    env = {"API_KEY": "raw-key"}
    resolved = auth_helpers.resolve_header_value("Key", "Bearer VALID_TOKEN", env)
    assert resolved == "raw-key"


def test_resolve_header_value_preserves_empty_authorization_for_auth_negative_case():
    case = {
        "category": "validation",
        "description": "Attempt GET task with empty Authorization header value",
        "request": {"headers": {"Authorization": ""}},
    }
    env = {"ACCESS_TOKEN": "secret-token"}
    resolved = auth_helpers.resolve_header_value("Authorization", "", env, case=case)
    assert resolved == ""


def test_apply_auth_headers_skips_empty_authorization_negative_case():
    case = {
        "category": "validation",
        "description": "Attempt POST task with empty Authorization header value",
        "request": {"headers": {"Authorization": "Bearer "}},
    }
    headers = auth_helpers.apply_auth_headers(
        {"Authorization": ""},
        case,
        {"ACCESS_TOKEN": "secret-token", "API_KEY": "api-key"},
    )
    assert headers.get("Authorization", "") == ""
    assert "Key" not in headers
