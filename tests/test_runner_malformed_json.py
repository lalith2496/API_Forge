import runner


def test_attach_malformed_json_string_body():
    kwargs = {}
    runner._attach_body_kwargs(
        kwargs,
        '{"broken": json',
        "application/json",
    )
    assert kwargs.get("data") == '{"broken": json'
    assert "json" not in kwargs
