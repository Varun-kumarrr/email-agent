from fastapi.testclient import TestClient

from app.main import app


def test_root_returns_running_message():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Email Agent API is running"}


def test_openapi_docs_available():
    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
