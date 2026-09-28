"""The email agent: loads the authenticated company's context, asks the LLM for
an email and returns it for the user to review. It never sends anything."""

import logging

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.models import Company
from app.repositories.company_repository import CompanyRepository
from app.schemas.agent import GenerateEmailRequest, GenerateEmailResponse
from app.services.agent.context import build_company_context
from app.services.agent.output_guard import guard_output
from app.services.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.services.email_config_service import EmailConfigService
from app.services.llm import LLMError, LLMProvider, LLMRequest, MockLLMProvider, get_llm_provider
from app.services.preferences_service import PreferencesService
from app.services.signature_service import SignatureService

logger = logging.getLogger(__name__)


class EmailAgentService:
    def __init__(self, db: Session, provider: LLMProvider | None = None):
        self.db = db
        self.provider = provider or get_llm_provider()

    def build_request(self, company: Company, data: GenerateEmailRequest) -> LLMRequest:
        # Reload with all child collections for this company only.
        company = CompanyRepository(self.db).get_by_user_id(company.user_id)
        context = build_company_context(
            company,
            config=EmailConfigService(self.db).find(company),
            preferences=PreferencesService(self.db).get(company),
            signature=SignatureService(self.db).find(company),
        )
        email_request = {
            "recipient_name": data.recipient_name,
            "recipient_email": data.recipient_email,
            "purpose": data.purpose,
            "tone": data.tone.value,
            "additional_instructions": data.additional_instructions,
        }
        user_prompt = build_user_prompt(context, email_request)
        mock_context = {
            **context,
            "recipient_name": data.recipient_name,
            "purpose": data.purpose,
            "tone": data.tone.value,
        }
        return LLMRequest(system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt, context=mock_context)

    def generate(self, company: Company, data: GenerateEmailRequest) -> GenerateEmailResponse:
        request = self.build_request(company, data)
        try:
            email = guard_output(self.provider.generate_email(request))
            return GenerateEmailResponse(subject=email.subject, body=email.body, provider=self.provider.name)
        except LLMError as error:
            logger.warning("LLM provider %s failed code=%s", self.provider.name, error.code)
            if not settings.LLM_FALLBACK_TO_MOCK or isinstance(self.provider, MockLLMProvider):
                raise ServiceUnavailableError(error.message, details={"code": error.code})
            email = guard_output(MockLLMProvider().generate_email(request))
            return GenerateEmailResponse(
                subject=email.subject,
                body=email.body,
                provider="mock",
                fallback_used=True,
                warning=f"{error.message} A template-based draft was generated instead.",
            )
