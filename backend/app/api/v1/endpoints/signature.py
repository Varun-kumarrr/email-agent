from fastapi import APIRouter, Response, status

from app.core.dependencies import CurrentCompany, DbSession
from app.schemas.signature import SignatureCreate, SignatureResponse, SignatureUpdate
from app.services.signature_service import SignatureService

router = APIRouter(prefix="/signature", tags=["Email Signature"])


@router.post("", response_model=SignatureResponse, status_code=status.HTTP_201_CREATED, summary="Create the company's email signature")
def create_signature(data: SignatureCreate, company: CurrentCompany, db: DbSession):
    return SignatureService(db).create(company, data)


@router.get("", response_model=SignatureResponse, summary="Get the company's email signature")
def get_signature(company: CurrentCompany, db: DbSession):
    return SignatureService(db).get(company)


@router.put("", response_model=SignatureResponse, summary="Update the company's email signature")
def update_signature(data: SignatureUpdate, company: CurrentCompany, db: DbSession):
    return SignatureService(db).update(company, data)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, summary="Delete the company's email signature")
def delete_signature(company: CurrentCompany, db: DbSession):
    SignatureService(db).delete(company)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
