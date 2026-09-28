from tests.test_company import create_company
from tests.test_email_config import create_config
from tests.test_isolation import XYZ_PROFILE
from tests.test_signature import PAYLOAD as SIGNATURE_PAYLOAD

PREFS = "/api/v1/preferences"
UPDATE = {
    "sender_name": "ABC Sales Team",
    "reply_to": "sales@abctech.com",
    "default_format": "HTML",
    "daily_send_limit": 50,
    "max_recipients_per_email": 5,
    "max_send_retries": 1,
    "default_cc": ["manager@abctech.com", "MANAGER@abctech.com"],
    "default_bcc": ["crm-log@abctech.com"],
    "extra_settings": {"track_opens": False},
}


def test_get_defaults_before_saving(client, auth_headers):
    create_company(client, auth_headers)
    body = client.get(PREFS, headers=auth_headers).json()
    assert body["default_format"] == "PLAIN_TEXT"
    assert body["daily_send_limit"] == 100
    assert body["default_cc"] == []
    assert body["signature"] == {"configured": False, "enabled": False, "append_automatically": False}
    assert body["sent_today"] == 0 and body["remaining_today"] == 100


def test_update_and_retrieve(client, auth_headers):
    create_company(client, auth_headers)
    response = client.put(PREFS, json=UPDATE, headers=auth_headers)
    assert response.status_code == 200, response.text
    body = client.get(PREFS, headers=auth_headers).json()
    assert body["sender_name"] == "ABC Sales Team"
    assert body["default_format"] == "HTML"
    assert body["default_cc"] == ["manager@abctech.com"]  # deduplicated, lowercased
    assert body["default_bcc"] == ["crm-log@abctech.com"]
    assert body["extra_settings"] == {"track_opens": False}
    assert body["remaining_today"] == 50


def test_effective_values_fall_back_to_email_config(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    body = client.get(PREFS, headers=auth_headers).json()
    assert body["effective_sender_name"] == "Anjali from ABC Technologies"
    assert body["effective_reply_to"] == "sales@abctech.com"

    client.put(PREFS, json=UPDATE, headers=auth_headers)
    body = client.get(PREFS, headers=auth_headers).json()
    assert body["effective_sender_name"] == "ABC Sales Team"


def test_signature_summary(client, auth_headers):
    create_company(client, auth_headers)
    client.post("/api/v1/signature", json=SIGNATURE_PAYLOAD, headers=auth_headers)
    body = client.get(PREFS, headers=auth_headers).json()
    assert body["signature"] == {"configured": True, "enabled": True, "append_automatically": True}


def test_preferences_validation(client, auth_headers):
    create_company(client, auth_headers)
    cases = [
        {**UPDATE, "default_format": "MARKDOWN"},
        {**UPDATE, "daily_send_limit": 0},
        {**UPDATE, "max_recipients_per_email": 500},
        {**UPDATE, "max_send_retries": -1},
        {**UPDATE, "default_cc": ["not-an-email"]},
        {**UPDATE, "reply_to": "bad"},
    ]
    for payload in cases:
        assert client.put(PREFS, json=payload, headers=auth_headers).status_code == 422, payload


def test_preferences_isolated(client, auth_headers, other_auth_headers):
    create_company(client, auth_headers)
    create_company(client, other_auth_headers, XYZ_PROFILE)
    client.put(PREFS, json=UPDATE, headers=auth_headers)
    assert client.get(PREFS, headers=other_auth_headers).json()["sender_name"] is None
