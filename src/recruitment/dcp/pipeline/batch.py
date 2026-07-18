from recruitment.shared.services.storage import get_file_bytes
from recruitment.shared.services.text_extractor import extract_text, extract_payslip_bytes
from recruitment.shared.services.database import get_candidate, save_results, update_verification_status
from recruitment.dcp.agents.categorizer import categorize
from recruitment.dcp.agents.experience import verify
from recruitment.dcp.agents.payslip import assess, calculate_salary_trend
from recruitment.dcp.types.documents import DocType
from recruitment.dcp.types.extraction import PayslipData
from recruitment.dcp.types.results import SalaryAssessment
from recruitment.shared.logging import logger

def run_batch(verification_id: str, s3_keys: list[str]) -> dict:
    logger.info("Batch started", verification_id=verification_id, doc_count=len(s3_keys))
    candidate = get_candidate(verification_id)

    # Step 1 — extract text and categorise each document
    # Process each payslip individually to avoid LLM confusion with multiple docs
    experience_docs: list[str] = []
    payslip_docs: list[tuple[str, bytes]] = []  # (s3_key, pdf_bytes)

    for s3_key in s3_keys:
        file_bytes = get_file_bytes(s3_key)
        # Categorise using extracted text (cheap, fast — works for native + scanned)
        text, method = extract_text(file_bytes)
        doc_type, categorization_time = categorize(text)
        logger.info("Document categorised",
                    s3_key=s3_key,
                    doc_type=doc_type,
                    method=method,
                    categorization_time_seconds=round(categorization_time, 2))

        if doc_type == DocType.PAYSLIP:
            # Store payslip with s3_key for individual extraction
            payslip_docs.append((s3_key, extract_payslip_bytes(file_bytes)))
        elif doc_type == DocType.EXPERIENCE_LETTER:
            experience_docs.append(text)
        else:
            logger.info("Skipping OTHER doc type", s3_key=s3_key)

    # Step 2 — Experience agent: receives plain text (PyMuPDF extracted)
    experience_result = verify(
        text=experience_docs,
        expected_years=candidate["expected_experience_years"],
    )

    # Step 3 — Payslip agent: extract each payslip individually, use most recent
    salary_assessment = None
    payslip_extractions: list[PayslipData] = []

    if payslip_docs:
        # Store both payslip data and its assessment for tracking
        payslip_results: list[tuple[PayslipData, SalaryAssessment]] = []

        for s3_key, pdf_bytes in payslip_docs:
            # Extract each payslip individually to avoid LLM confusion
            payslip_data, assessment = assess(
                pdf_docs=[pdf_bytes],
                expected_salary=candidate["expected_salary"],
                verification=experience_result,
                company_segment=candidate.get("company_segment", "MNC"),
            )

            logger.info("Payslip extracted", s3_key=s3_key, pay_period=payslip_data.pay_period, annual_ctc=payslip_data.annual_ctc)

            payslip_results.append((payslip_data, assessment))
            payslip_extractions.append(payslip_data)

        # Sort by pay_period descending (most recent first) for accurate trend analysis
        payslip_extractions.sort(key=lambda p: p.pay_period or "", reverse=True)
        payslip_results.sort(key=lambda x: x[0].pay_period or "", reverse=True)

        if payslip_results:
            # Most recent payslip — use its assessment for salary assessment
            most_recent_data, most_recent_assessment = payslip_results[0]
            salary_assessment = most_recent_assessment
            logger.info("Using most recent payslip", pay_period=most_recent_data.pay_period, annual_ctc=most_recent_data.annual_ctc)

        # Calculate recent salary increment/trend
        if len(payslip_extractions) > 1 and salary_assessment:
            salary_trend = calculate_salary_trend(payslip_extractions)
            if salary_trend:
                salary_assessment.recent_increment = salary_trend
                logger.info("Salary trend",
                           trend=salary_trend.trend,
                           change_amount=salary_trend.change_amount,
                           change_percentage=salary_trend.change_percentage,
                           change_confidence=salary_trend.change_confidence)

    # Persist and return
    results = {
        "verification_id": verification_id,
        "experience_verification": experience_result.model_dump(),
        "salary_assessment": salary_assessment.model_dump(),
    }
    save_results(verification_id, results["experience_verification"], results["salary_assessment"])
    update_verification_status(verification_id, "DONE")
    return results

