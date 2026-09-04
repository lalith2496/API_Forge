import postman_importer


def test_parse_minimal_postman_collection():
    data = {
        "info": {"name": "Demo", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [
            {
                "name": "Get users",
                "request": {
                    "method": "GET",
                    "header": [],
                    "url": {
                        "raw": "https://api.example.com/users?limit=10",
                        "protocol": "https",
                        "host": ["api", "example", "com"],
                        "path": ["users"],
                        "query": [{"key": "limit", "value": "10"}],
                    },
                },
            },
            {
                "name": "Create user",
                "request": {
                    "method": "POST",
                    "header": [{"key": "Content-Type", "value": "application/json"}],
                    "body": {"mode": "raw", "raw": "{\"name\":\"Ann\"}"},
                    "url": "https://api.example.com/users",
                },
            },
        ],
    }
    bundle = postman_importer.parse_collection(data)
    assert "error" not in bundle
    assert len(bundle["endpoints"]) == 2
    assert len(bundle["imported_cases"]) == 2
    post_case = bundle["imported_cases"][1]
    assert post_case["request"]["body"] == {"name": "Ann"}
