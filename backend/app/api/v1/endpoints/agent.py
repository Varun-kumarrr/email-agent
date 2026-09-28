from fastapi import APIRouter

from app.core.dependencies import LLM, CurrentCompany, DbSession
from app.schemas.agent import GenerateEmailRequest, GenerateEmailResponse
from app.services.agent.email_agent import EmailAgentService

router = APIRouter(prefix="/agent", tags=["AI Email Agent"])


@router.post(
    "/generate-email",
    response_model=GenerateEmailResponse,
    summary="Generate an email draft from the company profile",
    description=(
        "Loads the authenticated company's profile, signature, sender identity and preferences as "
        "context and asks the configured LLM for a draft. The draft is returned for review and "
        "editing; nothing is sent."
    ),
    responses={503: {"description": "AI provider unavailable and fallback disabled"}},
)
def generate_email(data: GenerateEmailRequest, company: CurrentCompany, db: DbSession, llm: LLM):
    return EmailAgentService(db, provider=llm).generate(company, data)
