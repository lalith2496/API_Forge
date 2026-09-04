import user_inputs


def test_build_request_params_catalog():
    suite = {
        "test_cases": [
            {
                "id": "TC-01",
                "category": "happy_path",
                "request": {
                    "query_params": {"status": "active", "limit": "10"},
                    "path_params": {"id": "123"},
                },
            },
            {
                "id": "TC-02",
                "category": "validation",
                "request": {
                    "query_params": {"status": "pending"},
                },
            },
        ]
    }
    catalog = user_inputs.build_request_params_catalog(suite)
    assert "query:status" in catalog
    assert "query:limit" in catalog
    assert "path:id" in catalog
    assert "TC-01" in catalog["query:status"]["cases"]
    assert "TC-02" not in catalog["query:status"]["cases"]


def test_apply_request_param_overrides_happy_path_only():
    req = {
        "query_params": {"status": "old"},
        "path_params": {"id": "1"},
    }
    updated = user_inputs.apply_request_param_overrides(
        req,
        {"query:status": "new", "path:id": "99", "query:extra": "nope"},
        case_category="happy_path",
    )
    assert updated["query_params"]["status"] == "new"
    assert updated["path_params"]["id"] == "99"
    assert "extra" not in updated["query_params"]


def test_apply_request_param_overrides_skips_validation_cases():
    req = {
        "query_params": {"contentIds": "00000000-0000-0000-0000-000000000000"},
        "path_params": {},
    }
    updated = user_inputs.apply_request_param_overrides(
        req,
        {"query:contentIds": "6a1e87f5259e22bdc9eb255b"},
        case_category="validation",
    )
    assert updated["query_params"]["contentIds"] == "00000000-0000-0000-0000-000000000000"


def test_apply_request_param_overrides():
    req = {
        "query_params": {"status": "old"},
        "path_params": {"id": "1"},
    }
    updated = user_inputs.apply_request_param_overrides(
        req,
        {"query:status": "new", "path:id": "99"},
        case_category="happy_path",
    )
    assert updated["query_params"]["status"] == "new"
    assert updated["path_params"]["id"] == "99"
