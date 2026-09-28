import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings
from app.core.security import create_access_token
from tests.conftest import DEFAULT_PASSWORD, register_and_login

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_register_returns_user_without_password(client):
    response = client.post(
        REGISTER, json={"email": "New@Example.com", "password": DEFAULT_PASSWORD, "name": " New User "}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["name"] == "New User"
    assert body["has_company"] is False
    assert "password" not in response.text
    assert "hashed_password" not in response.text


def test_duplicate_registration_is_conflict(client):
    payload = {"email": "dup@example.com", "password": DEFAULT_PASSWORD, "name": "Dup"}
    assert client.post(REGISTER, json=payload).status_code == 201
    payload["email"] = "DUP@example.com"  # case-insensitive
    response = client.post(REGISTER, json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_register_validation(client):
    bad = [
        {"email": "not-an-email", "password": DEFAULT_PASSWORD, "name": "X"},
        {"email": "a@example.com", "password": "short1", "name": "X"},
        {"email": "a@example.com", "password": "onlyletters", "name": "X"},
        {"email": "a@example.com", "password": DEFAULT_PASSWORD, "name": "   "},
    ]
    for payload in bad:
        assert client.post(REGISTER, json=payload).status_code == 422


def test_login_returns_token(client):
    client.post(REGISTER, json={"email": "l@example.com", "password": DEFAULT_PASSWORD, "name": "L"})
    response = client.post(LOGIN, json={"email": "l@example.com", "password": DEFAULT_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert body["user"]["email"] == "l@example.com"


def test_login_invalid_password_and_unknown_email_same_error(client):
    client.post(REGISTER, json={"email": "l@example.com", "password": DEFAULT_PASSWORD, "name": "L"})
    wrong = client.post(LOGIN, json={"email": "l@example.com", "password": "Wrong123"})
    unknown = client.post(LOGIN, json={"email": "nobody@example.com", "password": "Wrong123"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_with_valid_token(client):
    headers = register_and_login(client)
    response = client.get(ME, headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "anjali@abctech.com"


def test_protected_endpoint_requires_token(client):
    response = client.get(ME)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_jwt_rejected(client):
    response = client.get(ME, headers={"Authorization": "Bearer not.a.valid.token"})
    assert response.status_code == 401


def test_token_signed_with_other_secret_rejected(client):
    register_and_login(client)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=5), "type": "access"},
        "attacker-secret",
        algorithm="HS256",
    )
    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_jwt_rejected(client):
    register_and_login(client)
    user_id = client.post(LOGIN, json={"email": "anjali@abctech.com", "password": DEFAULT_PASSWORD}).json()["user"]["id"]
    token = create_access_token(uuid.UUID(user_id), expires_minutes=-1)
    response = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Token has expired"


def test_token_for_deleted_or_unknown_user_rejected(client):
    token = create_access_token(uuid.uuid4())
    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401
