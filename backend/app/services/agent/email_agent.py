"""The email agent.

Flow: load company -> profile -> signature -> preferences -> build context ->
generate -> validate -> return an editable draft. It never sends anything;
the user reviews/edits the draft and sends it via POST /emails/send.
"""

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.models import Company, EmailFormat
from app.repositories.company_repository import CompanyRepository
from app.schemas.agent import GenerateEmailRequest, GenerateEmailResponse
from app.services.agent.context import SIGNATURE_APPENDED_ON_SEND, build_company_context
from app.services.agent.output_guard import guard_output
from app.services.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.services.email_account_service import EmailAccountService
from app.services.email_composer import html_to_text
from app.services.llm import GeneratedEmail, LLMError, LLMProvider, LLMRequest, MockLLMProvider, get_llm_provider
from app.services.preferences_service import PreferencesService
from app.services.signature_service import SignatureService
from app.services.template_service import TemplateService, builtin_values, render_template
from app.utils.signature import strip_trailing_signature
from app.utils.template_render import strip_placeholders

logger = logging.getLogger(__name__)


class EmailAgentService:
    def __init__(self, db: Session, provider: LLMProvider | None = None):
        self.db = db
        self.provider = provider or get_llm_provider()

    def generate(self, company: Company, data: GenerateEmailRequest) -> GenerateEmailResponse:
        # 1-4. Load the company (with all profile collections), signature and preferences.
        company = CompanyRepository(self.db).get_by_user_id(company.user_id)
        preferences = PreferencesService(self.db).get(company)
        signature = SignatureService(self.db).find(company)

        account = self._sender_account(company, data)
        template = TemplateService(self.db).get_active(company, data.template_id) if data.template_id else None

        # 5. Build context.
        context = build_company_context(company, account=account, preferences=preferences, signature=signature)
        email_request = {
            "recipient_name": data.recipient_name,
            "recipient_email": data.recipient_email,
            "purpose": data.purpose,
            "tone": data.tone.value,
            "additional_instructions": data.additional_instructions,
        }
        missing_variables: list[str] = []
        if template is not None:
            # 5b. Render the optional template with built-in + user values; it goes to the model as data.
            values = builtin_values(
                company,
                account,
                sender_name=context["sender_name"],
                recipient_name=data.recipient_name,
                recipient_email=str(data.recipient_email),
            )
            values.update({k: v for k, v in data.template_variables.items() if v.strip()})
            subject, body, missing_variables = render_template(template, values)
            if template.content_type == EmailFormat.HTML:
                body = html_to_text(body)  # the model writes plain text; HTML is produced at send time
            email_request["template"] = {
                "name": template.name,
                "subject": subject,
                "body": body,
                "unfilled_placeholders": missing_variables,
            }
        request = LLMRequest(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(context, email_request),
            context={**context, **email_request},
        )

        # 6. Generate (with fallback) and validate.
        email, provider_name, fallback_used, warning = self._generate(request)
        if template is not None:  # never hand the user leftover {{ placeholders }}
            email = GeneratedEmail(strip_placeholders(email.subject) or email.subject, strip_placeholders(email.body))

        # 7. When the signature is appended on send, make sure the draft doesn't
        #    already contain it, so the recipient never sees it twice.
        policy = context["signature_policy"]
        if policy == SIGNATURE_APPENDED_ON_SEND and signature is not None:
            email = GeneratedEmail(email.subject, strip_trailing_signature(email.body, signature.signature_text))

        # 8. Return the editable draft.
        return GenerateEmailResponse(
            subject=email.subject,
            body=email.body,
            recipient_email=data.recipient_email,
            provider=provider_name,
            fallback_used=fallback_used,
            warning=warning,
            signature_policy=policy,
            signature_preview=signature.signature_text if policy == SIGNATURE_APPENDED_ON_SEND else None,
            suggested_format=template.content_type if template else preferences.default_format,
            suggested_cc=list(preferences.default_cc or []),
            suggested_bcc=list(preferences.default_bcc or []),
            template_id=template.id if template else None,
            missing_template_variables=missing_variables,
        )

    def _sender_account(self, company: Company, data: GenerateEmailRequest):
        """The account whose identity the draft is written for: the requested one or the default."""
        accounts = EmailAccountService(self.db)
        if data.email_account_id is not None:
            return accounts.get(company, data.email_account_id)  # 404 for other companies' accounts
        return accounts.default_account(company)

    def _generate(self, request: LLMRequest) -> tuple[GeneratedEmail, str, bool, str | None]:
        try:
            raw = self.provider.generate_email(request)
            # A provider chain reports which provider wrote the email, and a warning if it was not the first.
            return guard_output(raw), raw.provider or self.provider.name, raw.warning is not None, raw.warning
        except LLMError as error:
            logger.warning("LLM provider %s failed code=%s", self.provider.name, error.code)
            if not settings.LLM_FALLBACK_TO_MOCK or isinstance(self.provider, MockLLMProvider):
                raise ServiceUnavailableError(error.message, details={"code": error.code})
            email = guard_output(MockLLMProvider().generate_email(request))
            return email, "mock", True, f"{error.message} A template-based draft was generated instead."
