from recruitment.shared.services.storage import generate_presigned_upload_url
from recruitment.shared.services.database import (
    create_candidate_verification,
    get_candidate_verification,
    save_document_keys,
    save_results,
    update_verification_status,
)
from recruitment.dcp.pipeline.batch import run_batch
from recruitment.dcp.agents.payslip import predict_from_confirmed


def create_with_urls(
    candidate_id: str,
    candidate_name: str,
    expected_experience_years: float,
    expected_salary: float,
    currency: str,
    files: list[dict],
) -> dict:
    verification_id = create_candidate_verification(
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        expected_experience_years=expected_experience_years,
        expected_salary=expected_salary,
        currency=currency,
    )
    upload_urls = []
    for file in files:
        key = f"candidate_verifications/{candidate_id}/{verification_id}/{file['filename']}"
        url = generate_presigned_upload_url(key, file.get("content_type", "application/pdf"))
        upload_urls.append({"key": key, "url": url})
    return {"verification_id": verification_id, "upload_urls": upload_urls}


def start_processing(verification_id: str, keys: list[str]) -> dict:
    save_document_keys(verification_id, keys)
    run_batch(verification_id=verification_id, s3_keys=keys)
    return {"status": "processing"}


def fetch(verification_id: str) -> dict:
    return get_candidate_verification(verification_id)


def run_final_analysis(
    verification_id: str,
    experience_years: float,
    current_salary: float,
    expected_salary: float,
    currency: str = "INR",
    company_segment: str = "MNC",
) -> dict:
    assessment = predict_from_confirmed(
        current_salary=current_salary,
        expected_salary=expected_salary,
        experience_years=experience_years,
        currency=currency,
        company_segment=company_segment,
    )
    save_results(verification_id, {}, assessment.model_dump())
    update_verification_status(verification_id, "DONE")
    return {"verification_id": verification_id, "salary_assessment": assessment.model_dump()}
