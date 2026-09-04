import runner


def test_merge_request_overrides():
    req = {
        "headers": {"Accept": "application/json"},
        "query_params": {"a": "1"},
        "path_params": {"id": "old"},
        "body": {"x": 1},
    }
    merged = runner.merge_request_overrides(req, {
        "headers": {"Authorization": "Bearer x"},
        "query_params": {"a": "2"},
        "path_params": {"id": "new"},
        "body": {"x": 99},
    })
    assert merged["headers"]["Authorization"] == "Bearer x"
    assert merged["query_params"]["a"] == "2"
    assert merged["path_params"]["id"] == "new"
    assert merged["body"]["x"] == 99
