from app.core.encryption import decrypt_secret, encrypt_secret
from app.models import EmailConfiguration
from tests.test_company import create_company

CONFIG = "/api/v1/email-config"
SMTP_PASSWORD = "app-password-that-must-never-leak"

SMTP_SETTINGS = {
    "email": "anjali@abctech.com",
    "smtp_host": "smtp.abctech.com",
    "smtp_port": 587,
    "username": "anjali@abctech.com",
    "password": SMTP_PASSWORD,
    "security_type": "STARTTLS",
    "sender_name": "Anjali from ABC Technologies",
    "reply_to": "sales@abctech.com",
}


def create_config(client, headers, settings=None):
    response = client.post(CONFIG, json=settings or SMTP_SETTINGS, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_encryption_roundtrip_is_not_plaintext():
    token = encrypt_secret("secret-value")
    assert "secret-value" not in token
    assert decrypt_secret(token) == "secret-value"


def test_config_requires_company(client, auth_headers):
    response = client.post(CONFIG, json=SMTP_SETTINGS, headers=auth_headers)
    assert response.status_code == 404
    assert "company profile" in response.json()["error"]["message"].lower()


def test_create_config_never_returns_password(client, auth_headers, db_session):
    create_company(client, auth_headers)
    response = client.post(CONFIG, json=SMTP_SETTINGS, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["password_configured"] is True
    assert body["security_type"] == "STARTTLS"
    assert "password" not in body
    assert SMTP_PASSWORD not in response.text

    stored = db_session.query(EmailConfiguration).one()
    assert stored.encrypted_password != SMTP_PASSWORD
    assert decrypt_secret(stored.encrypted_password) == SMTP_PASSWORD


def test_get_config_never_returns_password(client, auth_headers):
    create_company(client, auth_headers)
    assert client.get(CONFIG, headers=auth_headers).status_code == 404
    create_config(client, auth_headers)
    response = client.get(CONFIG, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["password_configured"] is True
    assert SMTP_PASSWORD not in response.text


def test_update_without_password_preserves_it(client, auth_headers, db_session):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    update = {k: v for k, v in SMTP_SETTINGS.items() if k != "password"}
    update["sender_name"] = "ABC Sales"
    response = client.put(CONFIG, json=update, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["sender_name"] == "ABC Sales"
    assert SMTP_PASSWORD not in response.text
    stored = db_session.query(EmailConfiguration).one()
    db_session.refresh(stored)
    assert decrypt_secret(stored.encrypted_password) == SMTP_PASSWORD


def test_update_with_password_replaces_it(client, auth_headers, db_session):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    response = client.put(CONFIG, json={**SMTP_SETTINGS, "password": "new-app-password"}, headers=auth_headers)
    assert response.status_code == 200
    assert "new-app-password" not in response.text
    stored = db_session.query(EmailConfiguration).one()
    db_session.refresh(stored)
    assert decrypt_secret(stored.encrypted_password) == "new-app-password"


def test_duplicate_create_is_conflict(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    assert client.post(CONFIG, json=SMTP_SETTINGS, headers=auth_headers).status_code == 409


def test_config_validation(client, auth_headers):
    create_company(client, auth_headers)
    cases = [
        {**SMTP_SETTINGS, "email": "bad"},
        {**SMTP_SETTINGS, "smtp_host": "https://smtp.example.com"},
        {**SMTP_SETTINGS, "smtp_host": "smtp example com"},
        {**SMTP_SETTINGS, "smtp_port": 0},
        {**SMTP_SETTINGS, "smtp_port": 70000},
        {**SMTP_SETTINGS, "security_type": "TLS1.0"},
        {**SMTP_SETTINGS, "password": ""},
        {**SMTP_SETTINGS, "reply_to": "nope"},
        {k: v for k, v in SMTP_SETTINGS.items() if k != "password"},  # password required on create
    ]
    for payload in cases:
        assert client.post(CONFIG, json=payload, headers=auth_headers).status_code == 422, payload


def test_validation_errors_do_not_echo_password(client, auth_headers):
    create_company(client, auth_headers)
    payload = {**SMTP_SETTINGS, "smtp_port": "not-a-port", "password": "x" * 600}
    response = client.post(CONFIG, json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert "x" * 600 not in response.text
    assert SMTP_PASSWORD not in response.text
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert {"password", "smtp_port"} <= fields


def test_openapi_response_schema_has_no_password():
    from app.main import app

    schemas = app.openapi()["components"]["schemas"]
    assert "password" not in schemas["EmailConfigResponse"]["properties"]
    assert "password_configured" in schemas["EmailConfigResponse"]["properties"]
    assert "hashed_password" not in schemas["UserResponse"]["properties"]
