"""Prompts for the email agent."""

import json
from typing import Any

SYSTEM_PROMPT = """You are an email-writing assistant for a business.
Write one email on behalf of the sender, using the company context provided.

Rules:
1. Use only facts that appear in the company context. Do not invent products, customers, prices, statistics, awards, partnerships, revenue, claims or features.
2. If the context lacks information the email would need, write around it; do not guess.
3. Address the recipient by name and follow the requested tone.
4. Keep the email concise, clear and professional. Plain text only, no markdown.
5. Respond with JSON: {"subject": "...", "body": "..."}.
"""


def build_user_prompt(context: dict[str, Any], *, recipient_name: str, recipient_email: str,
                      purpose: str, tone: str, additional_instructions: str | None) -> str:
    request = {
        "recipient_name": recipient_name,
        "recipient_email": recipient_email,
        "purpose": purpose,
        "tone": tone,
        "additional_instructions": additional_instructions,
    }
    return (
        "COMPANY CONTEXT:\n"
        f"{json.dumps(context, indent=2, ensure_ascii=False)}\n\n"
        "EMAIL REQUEST:\n"
        f"{json.dumps(request, indent=2, ensure_ascii=False)}\n"
    )
