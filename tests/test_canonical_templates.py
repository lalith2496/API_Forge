import canonical_templates


def test_full_schema_includes_optional_properties():
    schema = {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "nickname": {"type": "string"},
        },
    }
    body = canonical_templates._full_example_from_schema(schema)
    assert "name" in body
    assert "nickname" in body


def test_mutate_field_value_preserves_shape():
    body = {"user": {"email": "a@b.com", "role": "admin"}}
    mutated = canonical_templates.mutate_field_value(body, "user.email", "bad@evil.com")
    assert mutated["user"]["email"] == "bad@evil.com"
    assert mutated["user"]["role"] == "admin"
    assert body["user"]["email"] == "a@b.com"


def test_merge_canonical_into_body():
    existing = {"name": "Alice"}
    canonical = {"name": "Bob", "age": 30}
    merged = canonical_templates.merge_canonical_into_body(existing, canonical)
    assert merged["name"] == "Alice"
    assert merged["age"] == 30
