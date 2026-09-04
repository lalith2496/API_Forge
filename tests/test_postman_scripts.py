import postman_scripts


def test_build_test_script_includes_json_assertion():
    case = {
        "id": "TC-01",
        "expected": {
            "status_code": 200,
            "response_assertions": ["response is valid JSON"],
        },
    }
    script = "\n".join(postman_scripts.build_test_script(case))
    assert "pm.response.to.be.json" in script
    assert "status code is 200" in script


def test_build_test_script_includes_field_assertion():
    case = {
        "id": "TC-02",
        "expected": {
            "status_code": 201,
            "response_assertions": ['response contains field "id"'],
        },
    }
    script = "\n".join(postman_scripts.build_test_script(case))
    assert "_jsonHasKey" in script
    assert '"id"' in script
