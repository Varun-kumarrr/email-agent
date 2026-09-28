"""Builds the company context the email agent writes from.

Everything comes from the authenticated company's own records.
"""

from typing import Any

from app.models import Company, EmailConfiguration, EmailPreferences, EmailSignature


def build_company_context(
    company: Company,
    *,
    config: EmailConfiguration | None,
    preferences: EmailPreferences,
    signature: EmailSignature | None,
) -> dict[str, Any]:
    sender_name = preferences.sender_name or (config.sender_name if config else None) or company.contact_person
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
        "sender_name": sender_name,
        "sender_email": config.email if config else company.contact_email,
        "signature": signature.signature_text if signature and signature.enabled else None,
    }
