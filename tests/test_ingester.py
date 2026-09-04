import ingester


def test_resolve_servers_openapi3():
    spec = {
        "openapi": "3.0.0",
        "servers": [{"url": "https://api.example.com/v1"}],
    }
    assert ingester.ResolveServers(spec) == [{"url": "https://api.example.com/v1"}]


def test_resolve_servers_swagger2():
    spec = {
        "swagger": "2.0",
        "host": "petstore.swagger.io",
        "basePath": "/v2",
        "schemes": ["https", "http"],
    }
    servers = ingester.ResolveServers(spec)
    assert {"url": "https://petstore.swagger.io/v2"} in servers
    assert {"url": "http://petstore.swagger.io/v2"} in servers


def test_normalize_security_swagger2():
    spec = {
        "swagger": "2.0",
        "securityDefinitions": {
            "petstore_auth": {
                "type": "oauth2",
                "flow": "implicit",
                "authorizationUrl": "https://example.com/oauth/dialog",
                "scopes": {"write:pets": "modify pets"},
            }
        },
        "paths": {},
    }
    security = [{"petstore_auth": ["write:pets"]}]
    out = ingester.NormalizeSecurity(spec, security)
    assert len(out) == 1
    assert out[0]["name"] == "petstore_auth"
    assert out[0]["type"] == "oauth2"


def test_build_llm_payload_uses_swagger2_servers():
    spec = {
        "swagger": "2.0",
        "host": "api.example.com",
        "basePath": "/v1",
        "schemes": ["https"],
        "info": {"title": "Demo"},
        "paths": {
            "/items": {
                "get": {"responses": {"200": {"description": "ok"}}},
            }
        },
    }
    endpts = ingester.ListEndpoints(spec)
    norm_map = ingester.NormalizeEndpoints(spec, endpts)
    payload = ingester.BuildLLMPayload(spec, endpts, norm_map)
    assert payload["api"]["servers"][0]["url"] == "https://api.example.com/v1"
