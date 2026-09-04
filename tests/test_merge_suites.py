from llm import merge_suites


def test_merge_suites_dedupes_and_renumbers():
    s1 = {
        "test_suite_name": "A",
        "endpoints": [{"method": "GET", "path": "/a"}],
        "test_cases": [{"id": "TC-01", "description": "one"}],
    }
    s2 = {
        "test_suite_name": "B",
        "endpoints": [{"method": "GET", "path": "/a"}, {"method": "POST", "path": "/b"}],
        "test_cases": [
            {"id": "TC-01", "description": "dup"},
            {"id": "TC-99", "description": "two"},
        ],
    }
    merged = merge_suites.merge_suites(s1, s2)
    assert len(merged["test_cases"]) == 2
    assert merged["test_cases"][0]["id"] == "TC-01"
    assert merged["test_cases"][1]["id"] == "TC-02"
    assert len(merged["endpoints"]) == 2
