import curl_parser


def test_parse_simple_get_curl():
    cmd = "curl 'https://api.example.com/v1/items?status=active'"
    bundle = curl_parser.parse_curl(cmd)
    assert "error" not in bundle
    assert bundle["endpoints"][0]["method"] == "GET"
    assert bundle["base_url"] == "https://api.example.com"
    assert bundle["imported_cases"][0]["request"]["query_params"]["status"] == "active"


def test_parse_post_json_curl():
    cmd = (
        "curl -X POST 'https://api.example.com/users' "
        "-H 'Content-Type: application/json' "
        "-H 'Authorization: Bearer tok' "
        "-d '{\"name\":\"Bob\"}'"
    )
    bundle = curl_parser.parse_curl(cmd)
    assert bundle["endpoints"][0]["method"] == "POST"
    assert bundle["imported_cases"][0]["request"]["body"] == {"name": "Bob"}
    assert "Authorization" in bundle["imported_cases"][0]["request"]["headers"]
