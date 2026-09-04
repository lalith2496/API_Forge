import auth_helpers


def test_should_not_inject_for_auth_category():
    case = {"category": "auth"}
    assert auth_helpers.should_inject_auth(case, {}) is False


def test_should_inject_when_authorization_present_for_api_key():
    case = {"category": "happy_path"}
    assert auth_helpers.should_inject_auth(case, {"Authorization": "Bearer x"}) is True


def test_apply_bearer_token():
    case = {"category": "happy_path"}
    headers = auth_helpers.apply_auth_headers(
        {},
        case,
        {"ACCESS_TOKEN": "Bearer secret"},
    )
    assert headers["Authorization"] == "Bearer secret"


def test_apply_api_key_header():
    case = {"category": "happy_path"}
    headers = auth_helpers.apply_auth_headers(
        {},
        case,
        {"API_KEY": "key123"},
    )
    assert headers["Key"] == "key123"


def test_apply_both_token_and_api_key():
    case = {"category": "happy_path"}
    headers = auth_helpers.apply_auth_headers(
        {},
        case,
        {"ACCESS_TOKEN": "secret", "API_KEY": "key123"},
    )
    assert headers["Authorization"] == "Bearer secret"
    assert headers["Key"] == "key123"


def test_apply_skips_auth_tests():
    case = {"category": "auth"}
    headers = auth_helpers.apply_auth_headers(
        {},
        case,
        {"ACCESS_TOKEN": "secret", "API_KEY": "key123"},
    )
    assert "Authorization" not in headers
    assert "Key" not in headers
