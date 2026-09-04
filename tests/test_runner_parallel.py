import runner


def _case(case_id: str, category: str = "happy_path"):
    return {
        "id": case_id,
        "category": category,
        "description": "test",
        "endpoint": {"method": "GET", "path": "/"},
        "request": {"method": "GET", "path": "/", "headers": {}, "query_params": {}, "path_params": {}, "body": None},
        "expected": {"status_code": 200, "response_assertions": []},
    }


def test_run_cases_parallel_preserves_order(monkeypatch):
    calls = []

    def fake_run_case(case, base_url, user_vals, env_vals=None, timeout=10, **kwargs):
        calls.append(case["id"])
        return {
            "id": case["id"],
            "category": case.get("category"),
            "description": "",
            "expected_status": 200,
            "actual_status": 200,
            "passed": True,
            "response_time_ms": 1,
            "error": None,
            "assertion_failures": [],
            "request_url": base_url,
            "response_body": "{}",
            "skipped": False,
        }

    monkeypatch.setattr(runner, "run_case", fake_run_case)
    monkeypatch.setattr(runner, "validate_url", lambda url: (True, None))

    suite = {"test_cases": [_case("TC-01"), _case("TC-02"), _case("TC-03")]}
    results = runner.run_cases(
        suite,
        "https://example.com",
        {},
        concurrency=3,
    )
    assert [r["id"] for r in results] == ["TC-01", "TC-02", "TC-03"]
    assert len(calls) == 3


def test_category_filter_skips_unselected(monkeypatch):
    def fake_run_case(case, base_url, user_vals, env_vals=None, timeout=10, **kwargs):
        return {
            "id": case["id"],
            "category": case.get("category"),
            "description": "",
            "expected_status": 200,
            "actual_status": 200,
            "passed": True,
            "response_time_ms": 1,
            "error": None,
            "assertion_failures": [],
            "request_url": base_url,
            "response_body": "{}",
            "skipped": False,
        }

    monkeypatch.setattr(runner, "run_case", fake_run_case)
    monkeypatch.setattr(runner, "validate_url", lambda url: (True, None))

    suite = {
        "test_cases": [
            _case("TC-01", "happy_path"),
            _case("TC-02", "auth"),
        ]
    }
    results = runner.run_cases(
        suite,
        "https://example.com",
        {},
        categories_filter=["happy_path"],
        concurrency=1,
    )
    assert results[0]["passed"] is True or results[0].get("error")
    assert results[1].get("skipped") is True
