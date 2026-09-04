import schema_validator


def test_validate_object_required_fields():
    schema = {
        "type": "object",
        "required": ["id", "name"],
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
        },
    }
    ok, errors = schema_validator.validate_against_schema({"id": 1}, schema)
    assert not ok
    assert any("name" in e for e in errors)

    ok, errors = schema_validator.validate_against_schema({"id": 1, "name": "x"}, schema)
    assert ok
    assert errors == []


def test_response_schema_for_status():
    norm = {
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                    }
                }
            }
        }
    }
    schema = schema_validator.response_schema_for_status(norm, 200)
    assert schema is not None
    assert schema.get("type") == "object"
