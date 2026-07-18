from recruitment.shared.services.database import get_confirmed_categories, get_candidate_verification
from recruitment.dcp.pipeline.graph import pipeline
from recruitment.shared.logging import logger


def handler(event, context):
    verification_id = event["verification_id"]
    logger.info("Processing verification", verification_id=verification_id)

    confirmed_docs = get_confirmed_categories(verification_id)
    candidate = get_candidate_verification(verification_id)

    pipeline.invoke({
        "verification_id": verification_id,
        "candidate": candidate,
        "confirmed_docs": confirmed_docs,
        "experience_texts": [],
        "payslip_results": [],
        "experience_result": {},
        "salary_assessment": {},
    })
