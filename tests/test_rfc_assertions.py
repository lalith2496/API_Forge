import rfc_assertions


def test_problem_json_assertion_pass():
    body = '{"type":"about:blank","title":"Bad Request","status":400}'
    ok, _ = rfc_assertions.evaluate_rfc_assertion(
        {"type": "problem_json"},
        body,
        400,
        {"Content-Type": "application/problem+json"},
    )
    assert ok


def test_problem_json_assertion_fail_missing_title():
    body = '{"type":"about:blank","status":400}'
    ok, msg = rfc_assertions.evaluate_rfc_assertion(
        {"type": "problem_json"},
        body,
        400,
        {"Content-Type": "application/problem+json"},
    )
    assert not ok
    assert "title" in msg


def test_cookie_flags_assertion():
    ok, _ = rfc_assertions.evaluate_rfc_assertion(
        {"type": "cookie_flags", "require": ["Secure", "HttpOnly"]},
        "",
        200,
        {"Set-Cookie": "session=abc; Secure; HttpOnly; Path=/"},
    )
    assert ok
