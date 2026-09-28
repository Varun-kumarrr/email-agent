"""Deterministic offline provider.

Lets the whole workflow be demonstrated without an API key. It builds the email
only from the supplied company context, so it never invents facts either.
"""

from app.services.llm.base import GeneratedEmail, LLMProvider, LLMRequest


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


class MockLLMProvider(LLMProvider):
    name = "mock"

    def generate_email(self, request: LLMRequest) -> GeneratedEmail:
        ctx = request.context
        company = ctx.get("company", {})
        company_name = company.get("name") or "our company"
        services = [s["name"] for s in company.get("services", [])]
        customers = [c["segment"] for c in company.get("target_customers", [])]
        values = [v["statement"] for v in company.get("value_propositions", [])]
        recipient = ctx.get("recipient_name") or "there"
        purpose = (ctx.get("purpose") or "").strip()
        sender = ctx.get("sender_name") or company.get("contact_person") or company_name

        subject = f"{company_name}: {purpose[:60].rstrip('.')}" if purpose else f"Introducing {company_name}"

        paragraphs = [f"Hi {recipient},"]
        intro = f"I'm reaching out from {company_name}."
        if company.get("description"):
            intro += f" {company['description'].rstrip('.')}."
        paragraphs.append(intro)
        if purpose:
            paragraphs.append(f"The reason for my email: {purpose.rstrip('.')}.")
        if services:
            line = f"We offer {_join(services)}"
            line += f", designed for {_join(customers).lower()}." if customers else "."
            paragraphs.append(line)
        if values:
            paragraphs.append(f"Our aim is simple: {values[0].rstrip('.')}.")
        paragraphs.append("Would you be open to a short call to see whether this could help you?")

        body = "\n\n".join(paragraphs)
        policy = ctx.get("signature_policy", "none")
        if policy == "include_in_body" and ctx.get("signature"):
            body += "\n\n" + ctx["signature"]
        elif policy == "appended_on_send":
            body += "\n\nBest regards,"  # the saved signature is appended when sending
        else:
            body += f"\n\nBest regards,\n{sender}"
        return GeneratedEmail(subject=subject, body=body)
