"""Deterministic offline provider.

Lets the whole workflow be demonstrated without an API key. It builds the email
only from the supplied company context, so it never invents facts either.
It does not interpret the free-text purpose (that needs a real model); the UI
labels drafts from this provider so the user knows to edit them.
"""

from app.services.llm.base import GeneratedEmail, LLMProvider, LLMRequest


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


class MockLLMProvider(LLMProvider):
    name = "mock"

    def generate_email(self, request: LLMRequest) -> GeneratedEmail:
        ctx = request.context
        company = ctx.get("company", {})
        company_name = company.get("name") or "our company"
        services = [s["name"] for s in company.get("services", []) if s.get("name")]
        customers = [c["segment"] for c in company.get("target_customers", []) if c.get("segment")]
        values = [v["statement"] for v in company.get("value_propositions", []) if v.get("statement")]
        recipient = ctx.get("recipient_name") or "there"
        tone = ctx.get("tone", "professional")
        sender = ctx.get("sender_name") or company.get("contact_person")
        person = company.get("contact_person") or ctx.get("sender_name")  # who is "I" in the email

        if services and customers:
            subject = f"{company_name}: {services[0]} for {customers[0].lower()}"
        elif services:
            subject = f"{company_name}: {_join(services[:2])}"
        else:
            subject = f"Introducing {company_name}"

        greeting = f"Dear {recipient}," if tone == "formal" else f"Hi {recipient},"
        intro = f"I'm {person} from {company_name}." if person else f"I'm reaching out from {company_name}."
        if company.get("description"):
            intro += f" {_sentence(company['description'])}"
        paragraphs = [greeting, intro]

        if services:
            line = f"We offer {_join(services)}"
            line += f", built for {_join(customers).lower()}." if customers else "."
            paragraphs.append(line)
        if values:
            paragraphs.append(f"Our focus is simple: {_sentence(values[0][0].lower() + values[0][1:])}")

        paragraphs.append(
            "Would you be open to a short call next week to see whether this could help you?"
            if tone != "concise"
            else "Open to a quick call?"
        )

        body = "\n\n".join(paragraphs)
        policy = ctx.get("signature_policy", "none")
        if policy == "include_in_body" and ctx.get("signature"):
            body += "\n\n" + ctx["signature"]
        elif policy == "appended_on_send":
            # The saved signature is appended when sending; add a sign-off only if it lacks one.
            if not ctx.get("signature_includes_closing"):
                body += "\n\nBest regards,"
        else:
            body += "\n\nBest regards," + (f"\n{sender}" if sender else f"\n{company_name}")
        return GeneratedEmail(subject=subject, body=body)
