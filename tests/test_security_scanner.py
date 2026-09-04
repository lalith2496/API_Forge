import security_scanner


def test_scan_finds_missing_security_headers():
    results = [
        {
            "id": "TC-01",
            "category": "happy_path",
            "actual_status": 200,
            "skipped": False,
            "response_headers": {"Content-Type": "application/json"},
        }
    ]
    scan = security_scanner.scan_run_results(results, environment="DEV")
    rule_ids = {f["rule_id"] for f in scan["findings"]}
    assert "header_missing_strict-transport-security" in rule_ids
    assert scan["score"] < 100


def test_scan_cors_wildcard():
    results = [
        {
            "id": "TC-01",
            "category": "happy_path",
            "actual_status": 200,
            "skipped": False,
            "response_headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": "true",
            },
        }
    ]
    scan = security_scanner.scan_run_results(results)
    assert any(f["rule_id"] == "cors_wildcard_credentials" for f in scan["findings"])
