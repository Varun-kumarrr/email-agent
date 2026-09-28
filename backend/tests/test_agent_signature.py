import json
import re

import pytest

from app.core.dependencies import get_llm
from app.main import app
from app.schemas.signature import EXAMPLE_SIGNATURE
from app.services.llm import MockLLMProvider
from app.utils.signature import append_signature, ends_with_signature, strip_trailing_signature
from tests.fakes import RecordingLLM
from tests.test_agent import GENERATE, REQUEST
from tests.test_company import create_company
from tests.test_email_config import create_config
from tests.test_preferences import UPDATE as PREFS_UPDATE

SIGNATURE = "/api/v1/signature"


@pytest.fixture()
def llm():
    fake = RecordingLLM()
    app.dependency_overrides[get_llm] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm, None)


@pytest.fixture()
def mock_llm():
    app.dependency_overrides[get_llm] = lambda: MockLLMProvider()
    yield
    app.dependency_overrides.pop(get_llm, None)


@pytest.fixture()
def company(client, auth_headers):
    create_company(client, auth_headers)
    create_config(client, auth_headers)
    return auth_headers


def _context(llm):
    block = re.search(r"<company_context>\n(.*)\n</company_context>", llm.last.user_prompt, re.S).group(1)
    return json.loads(block)


def _set_signature(client, headers, enabled=True, append=True):
    client.post(
        SIGNATURE,
        json={"signature_text": EXAMPLE_SIGNATURE, "enabled": enabled, "append_automatically": append},
        headers=headers,
    )


def test_auto_append_signature_is_previewed_not_duplicated(client, company, mock_llm):
    _set_signature(client, company, append=True)
    body = client.post(GENERATE, json=REQUEST, headers=company).json()
    assert body["signature_policy"] == "appended_on_send"
    assert body["signature_preview"] == EXAMPLE_SIGNATURE
    assert "Business Development Manager" not in body["body"]  # added at send time instead
    # The saved signature starts with "Best Regards," so the draft has no closing of its own.
    assert "regards" not in body["body"].lower()


def test_manual_signature_is_included_in_editable_body(client, company, mock_llm):
    _set_signature(client, company, append=False)
    body = client.post(GENERATE, json=REQUEST, headers=company).json()
    assert body["signature_policy"] == "include_in_body"
    assert body["signature_preview"] is None
    assert body["body"].endswith(EXAMPLE_SIGNATURE)


def test_disabled_signature_is_not_used(client, company, llm):
    _set_signature(client, company, enabled=False)
    body = client.post(GENERATE, json=REQUEST, headers=company).json()
    assert body["signature_policy"] == "none"
    assert _context(llm)["signature"] is None
    assert "Business Development Manager" not in llm.last.user_prompt


def test_model_output_with_signature_is_deduplicated(client, company, llm):
    _set_signature(client, company, append=True)
    llm.body = "Hi Priya,\n\nHello there.\n\n" + EXAMPLE_SIGNATURE
    body = client.post(GENERATE, json=REQUEST, headers=company).json()
    assert body["body"] == "Hi Priya,\n\nHello there."


def test_preferences_shape_context_and_draft(client, company, llm):
    client.put("/api/v1/preferences", json=PREFS_UPDATE, headers=company)
    body = client.post(GENERATE, json=REQUEST, headers=company).json()
    context = _context(llm)
    assert context["sender_name"] == "ABC Sales Team"  # preference overrides config
    assert context["reply_to"] == "sales@abctech.com"
    assert body["suggested_format"] == "HTML"
    assert body["suggested_cc"] == ["manager@abctech.com"]
    assert body["suggested_bcc"] == ["crm-log@abctech.com"]
    assert body["recipient_email"] == REQUEST["recipient_email"]


def test_generation_does_not_send_or_record_anything(client, company, llm):
    client.post(GENERATE, json=REQUEST, headers=company)
    prefs = client.get("/api/v1/preferences", headers=company).json()
    assert prefs["sent_today"] == 0


def test_signature_without_closing_gets_closing_line(client, company, mock_llm):
    client.post(
        SIGNATURE,
        json={"signature_text": "Anjali\nABC Technologies", "enabled": True, "append_automatically": True},
        headers=company,
    )
    body = client.post(GENERATE, json=REQUEST, headers=company).json()
    assert body["body"].rstrip().endswith("Best regards,")


def test_closing_helpers():
    from app.utils.signature import is_closing_line, signature_has_closing

    for line in ["Best regards,", "Regards", "Kind regards,", "Thanks!", "Thank you,", "Sincerely,", "Cheers"]:
        assert is_closing_line(line), line
    assert not is_closing_line("Best of luck with the launch.")
    assert signature_has_closing("Best Regards,\nAnjali")
    assert not signature_has_closing("Anjali\nABC")
    body = "Hi,\n\nText\n\nBest regards,"
    assert append_signature(body, "Best Regards,\nAnjali") == "Hi,\n\nText\n\nBest Regards,\nAnjali"
    assert append_signature(body, "Anjali") == "Hi,\n\nText\n\nBest regards,\n\nAnjali"


def test_signature_helpers():
    body = "Hi,\n\nText"
    signed = append_signature(body, "Thanks,\nA")
    assert signed == "Hi,\n\nText\n\nThanks,\nA"
    assert append_signature(signed, "Thanks,\nA") == signed  # idempotent
    assert ends_with_signature(signed + "  \n", "Thanks,\nA")
    assert strip_trailing_signature(signed, "Thanks,\nA") == body
