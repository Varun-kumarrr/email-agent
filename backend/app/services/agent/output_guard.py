"""Validation of LLM output before it reaches the user.

- The subject becomes an email header, so it must be one line (prevents header
  injection such as "Subject\\r\\nBcc: attacker@example.com").
- Output that echoes the system prompt is rejected.
- Lengths are capped.
"""

import re

from app.services.agent.prompts import SYSTEM_PROMPT_CANARY
from app.services.llm import GeneratedEmail, LLMError
from app.utils.text import to_single_line

MAX_SUBJECT = 200
MAX_BODY = 10000


def clean_subject(subject: str) -> str:
    subject = re.sub(r"\s{2,}", " ", to_single_line(subject)).strip()
    return subject[:MAX_SUBJECT]


def guard_output(email: GeneratedEmail) -> GeneratedEmail:
    if SYSTEM_PROMPT_CANARY.lower() in (email.subject + email.body).lower():
        raise LLMError("The AI response was rejected by a safety check.", code="llm_unsafe_output")
    subject = clean_subject(email.subject)
    body = email.body.replace("\r\n", "\n").strip()[:MAX_BODY]
    if not subject or not body:
        raise LLMError("The AI provider returned an empty email.", code="llm_bad_response")
    return GeneratedEmail(subject=subject, body=body)
