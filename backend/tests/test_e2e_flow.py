"""End-to-end integration test of the whole assignment workflow through the API.

register -> login -> company profile -> SMTP configuration -> SMTP test ->
signature -> preferences -> AI generation -> user edit -> send -> history ->
company isolation. SMTP is a fake server and the LLM is the offline mock.
"""

from tests.conftest import register_and_login
from tests.fakes import install_fake_smtp
from tests.test_company import ABC_PROFILE
from tests.test_email_config import SMTP_PASSWORD, SMTP_SETTINGS
from tests.test_isolation import XYZ_PROFILE, XYZ_SMTP
from app.schemas.signature import EXAMPLE_SIGNATURE


def test_complete_workflow(client, monkeypatch):
    smtp = install_fake_smtp(monkeypatch)

    # 1-2. Register and log in
    headers = register_and_login(client, email="anjali@abctech.com", name="Anjali")
    assert client.get("/api/v1/auth/me", headers=headers).json()["has_company"] is False

    # 3. Company profile
    assert client.post("/api/v1/company", json=ABC_PROFILE, headers=headers).status_code == 201

    # 4. SMTP configuration (password never returned)
    config = client.post("/api/v1/email-config", json=SMTP_SETTINGS, headers=headers)
    assert config.status_code == 201 and SMTP_PASSWORD not in config.text

    # 5. SMTP test
    test = client.post("/api/v1/email-config/test", json={"recipient": "anjali@abctech.com"}, headers=headers)
    assert test.json()["success"] is True

    # 6. Signature
    client.post(
        "/api/v1/signature",
        json={"signature_text": EXAMPLE_SIGNATURE, "enabled": True, "append_automatically": True},
        headers=headers,
    )

    # 7. Preferences
    prefs = {
        "sender_name": "ABC Sales Team",
        "reply_to": "sales@abctech.com",
        "default_format": "HTML",
        "daily_send_limit": 20,
        "max_recipients_per_email": 5,
        "max_send_retries": 1,
        "default_cc": [],
        "default_bcc": ["crm-log@abctech.com"],
        "extra_settings": {},
    }
    assert client.put("/api/v1/preferences", json=prefs, headers=headers).status_code == 200

    # 8. AI generation from the company context
    draft = client.post(
        "/api/v1/agent/generate-email",
        json={
            "recipient_name": "Priya",
            "recipient_email": "priya@smallbiz.in",
            "purpose": "Write a professional cold email introducing our CRM to a small business owner.",
            "tone": "professional",
        },
        headers=headers,
    ).json()
    assert "ABC Technologies" in draft["body"]
    assert draft["signature_policy"] == "appended_on_send"
    assert smtp.sent[1:] == []  # generating never sends

    # 9. User reviews and edits
    edited_body = draft["body"].replace("Hi Priya,", "Hi Priya,\n\nGreat meeting you at the expo.")

    # 10. Send through the company's own SMTP account
    sent = client.post(
        "/api/v1/emails/send",
        json={
            "recipient": draft["recipient_email"],
            "subject": draft["subject"],
            "body": edited_body,
            "format": draft["suggested_format"],
            "cc": draft["suggested_cc"],
            "bcc": draft["suggested_bcc"],
        },
        headers=headers,
    )
    assert sent.status_code == 200, sent.text
    message = smtp.sent[-1]
    assert message["From"] == "ABC Sales Team <anjali@abctech.com>"
    assert message["Reply-To"] == "sales@abctech.com"
    assert message["Bcc"] is None and "crm-log@abctech.com" in smtp.envelopes[-1]
    text = message.get_body(preferencelist=("plain",)).get_content()
    assert "Great meeting you at the expo." in text
    assert text.count("Business Development Manager") == 1
    assert smtp.last.host == "smtp.abctech.com"

    # 11. History
    history = client.get("/api/v1/emails/history", headers=headers).json()
    assert history["total"] == 1
    assert history["items"][0]["status"] == "SENT"
    assert history["items"][0]["sender_email"] == "anjali@abctech.com"

    # 12. Company isolation: a second company sees none of this and sends via its own SMTP
    other = register_and_login(client, email="rahul@xyzcorp.com", name="Rahul")
    client.post("/api/v1/company", json=XYZ_PROFILE, headers=other)
    client.post("/api/v1/email-config", json={**XYZ_SMTP, "password": "xyz-pass"}, headers=other)
    assert client.get("/api/v1/emails/history", headers=other).json()["total"] == 0
    assert client.get("/api/v1/signature", headers=other).status_code == 404
    client.post(
        "/api/v1/emails/send",
        json={"recipient": "lead@example.com", "subject": "Hello", "body": "Hi"},
        headers=other,
    )
    assert smtp.last.host == "smtp.xyzcorp.com"
    assert "rahul@xyzcorp.com" in smtp.sent[-1]["From"]
    assert client.get("/api/v1/emails/history", headers=headers).json()["total"] == 1
