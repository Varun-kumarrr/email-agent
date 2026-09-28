from app.main import app


def test_swagger_and_redoc_available(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_every_endpoint_documented_with_summary_and_tag():
    schema = app.openapi()
    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            assert operation.get("summary"), f"{method.upper()} {path} has no summary"
            assert operation.get("tags"), f"{method.upper()} {path} has no tag"


def test_bearer_auth_documented():
    schema = app.openapi()
    schemes = schema["components"]["securitySchemes"]
    assert any(s.get("scheme") == "bearer" for s in schemes.values())
    assert "security" in schema["paths"]["/api/v1/company"]["get"]


def test_no_response_schema_exposes_secrets():
    schemas = app.openapi()["components"]["schemas"]
    for name, definition in schemas.items():
        if "Response" not in name and "Item" not in name and "Page" not in name:
            continue
        properties = set(definition.get("properties", {}))
        assert not properties & {"password", "hashed_password", "encrypted_password", "api_key", "secret_key"}, name


def test_error_responses_documented():
    op = app.openapi()["paths"]["/api/v1/emails/send"]["post"]
    assert {"401", "422", "502"} <= set(op["responses"])
