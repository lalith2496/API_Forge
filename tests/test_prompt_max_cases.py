from llm import prompt


def test_prompt_respects_max_cases():
    p10 = prompt.build_multi_prompt({"endpoints": [{"method": "GET", "path": "/"}]}, max_cases=10)
    assert "HARD MAXIMUM: 10 test cases" in p10
    assert "HARD MINIMUM: 10 test cases" in p10

    p50 = prompt.build_multi_prompt(
        {"endpoints": [{"method": "GET", "path": "/a"}, {"method": "POST", "path": "/b"}]},
        max_cases=50,
    )
    assert "HARD MAXIMUM: 50 test cases" in p50
    assert "HARD MINIMUM: 50 test cases" in p50


def test_prompt_clamps_bounds():
    p = prompt.build_multi_prompt({"endpoints": []}, max_cases=999)
    assert "HARD MAXIMUM: 50 test cases" in p


def test_prompt_focus_modes():
    core = prompt.build_multi_prompt({"endpoints": []}, max_cases=20, focus="core")
    assert "happy_path and auth" in core

    negative = prompt.build_multi_prompt({"endpoints": []}, max_cases=20, focus="negative")
    assert "validation, boundary" in negative

    security = prompt.build_multi_prompt({"endpoints": []}, max_cases=20, focus="security")
    assert "SQL injection" in security

    rfc = prompt.build_multi_prompt({"endpoints": []}, max_cases=20, focus="rfc")
    assert "RFC 9110" in rfc
