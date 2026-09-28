"""Builds the company context the email agent writes from.

Everything comes from the authenticated company's own records.
"""

from typing import Any

from app.models import Company, EmailAccount, EmailPreferences, EmailSignature
from app.utils.signature import signature_has_closing

# How the saved signature relates to the generated body:
SIGNATURE_APPENDED_ON_SEND = "appended_on_send"  # enabled + append automatically: added when sending
SIGNATURE_IN_BODY = "include_in_body"  # enabled, manual: the draft ends with it so the user can edit it
SIGNATURE_NONE = "none"  # no (enabled) signature: close with the sender name


def signature_policy(signature: EmailSignature | None) -> str:
    if signature is None or not signature.enabled:
        return SIGNATURE_NONE
    return SIGNATURE_APPENDED_ON_SEND if signature.append_automatically else SIGNATURE_IN_BODY


def resolve_sender_name(
    company: Company, account: EmailAccount | None, preferences: EmailPreferences
) -> str | None:
    return preferences.sender_name or (account.sender_name if account else None) or company.contact_person


def build_company_context(
    company: Company,
    *,
    account: EmailAccount | None,
    preferences: EmailPreferences,
    signature: EmailSignature | None,
) -> dict[str, Any]:
    policy = signature_policy(signature)
    return {
        "company": {
            "name": company.name,
            "description": company.description,
            "website": company.website,
            "industry": company.industry,
            "location": company.location,
            "services": [{"name": s.name, "description": s.description} for s in company.services],
            "target_customers": [
                {"segment": t.segment, "description": t.description} for t in company.target_customers
            ],
            "value_propositions": [{"statement": v.statement} for v in company.value_propositions],
            "contact": {
                "person": company.contact_person,
                "email": company.contact_email,
                "phone": company.contact_phone,
                "address": company.address,
            },
            "social_links": [{"platform": l.platform, "url": l.url} for l in company.social_links],
        },
        "sender_name": resolve_sender_name(company, account, preferences),
        "sender_email": account.email_address if account else company.contact_email,
        "reply_to": preferences.reply_to or (account.reply_to if account else None),
        "signature": signature.signature_text if policy != SIGNATURE_NONE else None,
        "signature_policy": policy,
        "signature_includes_closing": bool(
            policy != SIGNATURE_NONE and signature and signature_has_closing(signature.signature_text)
        ),
    }
