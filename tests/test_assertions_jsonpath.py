import assertions


def test_jsonpath_exists():
    data = {"data": {"id": 1}}
    ok, val = assertions.jsonpath_resolve(data, "$.data.id")
    assert ok
    assert val == 1


def test_jsonpath_equals_structured():
    ok, _ = assertions.evaluate_structured_assertion(
        {"type": "jsonpath_equals", "path": "$.status", "value": "ok"},
        '{"status": "ok"}',
    )
    assert ok


def test_max_response_ms_structured():
    ok, _ = assertions.evaluate_structured_assertion(
        {"type": "max_response_ms", "value": 500},
        "{}",
        response_time_ms=200,
    )
    assert ok

    ok, msg = assertions.evaluate_structured_assertion(
        {"type": "max_response_ms", "value": 100},
        "{}",
        response_time_ms=200,
    )
    assert not ok


def test_header_equals_structured():
    ok, _ = assertions.evaluate_structured_assertion(
        {"type": "header_equals", "name": "Content-Type", "contains": "json"},
        "{}",
        response_headers={"Content-Type": "application/json"},
    )
    assert ok
