import assertions


def test_valid_json_assertion_passes():
    ok, _ = assertions.evaluate_assertion(
        "response is valid JSON",
        '{"id": 1, "name": "test"}',
    )
    assert ok


def test_valid_json_assertion_fails():
    ok, msg = assertions.evaluate_assertion("response is valid JSON", "not json")
    assert not ok
    assert "invalid JSON" in msg


def test_field_exists_assertion():
    ok, _ = assertions.evaluate_assertion(
        'response contains field "id"',
        '{"id": 42}',
    )
    assert ok

    ok, msg = assertions.evaluate_assertion(
        'response contains field "missing"',
        '{"id": 42}',
    )
    assert not ok
    assert "missing" in msg


def test_not_empty_assertion():
    ok, _ = assertions.evaluate_assertion("response is not empty", '{"a": 1}')
    assert ok

    ok, _ = assertions.evaluate_assertion("response is not empty", "")
    assert not ok


def test_evaluate_assertions_empty_list():
    ok, failures = assertions.evaluate_assertions([], '{"x": 1}')
    assert ok
    assert failures == []
