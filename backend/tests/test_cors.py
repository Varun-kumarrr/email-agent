from app.core.config import settings


def _preflight(client, origin):
    return client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_allowed_origin_gets_cors_headers(client):
    origin = settings.ALLOWED_ORIGINS[0]
    response = _preflight(client, origin)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unknown_origin_is_not_allowed(client):
    response = _preflight(client, "https://evil.example.com")
    assert response.headers.get("access-control-allow-origin") is None
    simple = client.get("/", headers={"Origin": "https://evil.example.com"})
    assert simple.headers.get("access-control-allow-origin") is None


def test_wildcard_origin_is_filtered_out():
    from app.main import app


    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "*" not in cors.kwargs["allow_origins"]


def test_patch_and_delete_are_allowed_for_the_frontend_origin(client):
    origin = settings.ALLOWED_ORIGINS[0]
    for method in ("PATCH", "DELETE", "PUT"):
        response = client.options(
            "/api/v1/email-accounts/00000000-0000-0000-0000-000000000000",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200, method
        assert method in response.headers["access-control-allow-methods"]
