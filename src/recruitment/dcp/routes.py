"""Candidate Document Verification (DCP) API routes."""
import json

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from recruitment.dcp.controllers.candidate_verification_controller import (
    create_with_urls,
    fetch,
    run_final_analysis,
)
from recruitment.shared.config import settings
from recruitment.shared.logging import logger
from recruitment.shared.services.storage import get_file_bytes
from recruitment.shared.services.text_extractor import extract_text
from recruitment.shared.services.database import save_confirmed_categories, get_candidate_verification
from recruitment.dcp.agents.categorizer import categorize

router = APIRouter(prefix="/dcp", tags=["Candidate Document Verification"])

lambda_client = boto3.client("lambda")


class FileSpec(BaseModel):
    filename: str
    content_type: str = "application/pdf"


class CreateVerificationRequest(BaseModel):
    candidate_id: str
    candidate_name: str
    expected_experience_years: float
    expected_salary: float
    currency: str = "INR"
    files: list[FileSpec]


class StartVerificationRequest(BaseModel):
    verification_id: str
    keys: list[str]


class ConfirmedDoc(BaseModel):
    s3_key: str
    doc_type: str


class ConfirmCategoriesRequest(BaseModel):
    verification_id: str
    confirmed_categories: list[ConfirmedDoc]


@router.post("/create_verification", status_code=201)
def create_verification(req: CreateVerificationRequest):
    return create_with_urls(
        candidate_id=req.candidate_id,
        candidate_name=req.candidate_name,
        expected_experience_years=req.expected_experience_years,
        expected_salary=req.expected_salary,
        currency=req.currency,
        files=[f.model_dump() for f in req.files],
    )


@router.post("/start_verification", status_code=202)
def start_verification(req: StartVerificationRequest):
    categories = []
    for key in req.keys:
        file_bytes = get_file_bytes(key)
        text, _ = extract_text(file_bytes)
        doc_type, _ = categorize(text)
        categories.append({
            "s3_key": key,
            "filename": key.split("/")[-1],
            "ai_category": doc_type,
        })
    return {"verification_id": req.verification_id, "categories": categories}


@router.post("/confirm_categories", status_code=202)
def confirm_categories(req: ConfirmCategoriesRequest):
    confirmed = [d.model_dump() for d in req.confirmed_categories]
    save_confirmed_categories(req.verification_id, confirmed)

    if settings.local_mode:
        from recruitment.dcp.handlers.process_verification import handler as process_handler
        process_handler({"verification_id": req.verification_id}, None)
        return {"status": "done", "verification_id": req.verification_id}

    lambda_client.invoke(
        FunctionName=settings.cdv_verification_function_name,
        InvocationType="Event",
        Payload=json.dumps({"verification_id": req.verification_id}),
    )
    return {"status": "processing", "verification_id": req.verification_id}


class ConfirmExtractionRequest(BaseModel):
    verification_id: str
    experience_years: float
    current_salary: float
    expected_salary: float
    currency: str = "INR"


@router.post("/confirm_extraction", status_code=200)
def confirm_extraction(req: ConfirmExtractionRequest):
    candidate = get_candidate_verification(req.verification_id)
    return run_final_analysis(
        verification_id=req.verification_id,
        experience_years=req.experience_years,
        current_salary=req.current_salary,
        expected_salary=req.expected_salary,
        currency=req.currency,
        company_segment=candidate.get("company_segment", "MNC"),
    )


@router.get("/get_verification/{verification_id}")
def get_verification(verification_id: str):
    result = fetch(verification_id)
    if result.get("error") == "not found":
        raise HTTPException(status_code=404, detail="verification not found")
    return result

@router.get("/health")
def health():
    return {"status": "working"}
