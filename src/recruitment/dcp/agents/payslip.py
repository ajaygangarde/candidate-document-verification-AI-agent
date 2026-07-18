from recruitment.shared.config import settings
from recruitment.shared.services.llm import converse
from recruitment.dcp.types.extraction import PayslipData
from recruitment.dcp.types.results import SalaryAssessment, ExperienceVerification, RecentIncrement
from recruitment.shared.logging import logger


def extract_payslip(pdf_docs: list[bytes]) -> tuple[PayslipData, float]:
    """Send raw PDF bytes directly to the LLM via Converse — preserves table layout.

    Returns: (PayslipData, extraction_time_seconds)
    """
    content: list[dict] = [
        {
            "document": {
                "name": f"payslip_{i + 1}",
                "format": "pdf",
                "source": {"bytes": pdf_bytes},
            }
        }
        for i, pdf_bytes in enumerate(pdf_docs)
    ]
    content.append({
        "text": """Extract salary details from the payslip document(s).
If multiple payslips are provided, use only the MOST RECENT pay period.

RULES FOR annual_ctc — payslips use multiple formats, apply in priority order:

1. Annual Summary section present (large organizations):
   Look for "Annual Summary", "Form 16 Summary", "Income Tax Summary", or "Year-to-Date" section.
   Use the "Gross Salary" or "Total Compensation" field from that section.
   Example: 28,25,655 → annual_ctc = 2825655

2. Income Tax Calculation section prespent (mid-size organizations):
   Look for an annual projection table with "Annual" or "Projected Annual" columns.
   Use the "Total" or "Annual Total" row.
   Example: 18,58,315 → annual_ctc = 1858315

3. "CTC Monthly" or "Monthly CTC" field present:
   Some payslips explicitly show monthly CTC. Multiply by 12.
   Example: 1,02,500 → annual_ctc = 1230000

4. No annual section (use monthly calculation):
   Use Total Earnings (monthly gross, before deductions) × 12.
   Example: 15,000 × 12 → annual_ctc = 180000

RULES FOR monthly_earnings:
   Always use "Total Earnings" or "Gross Pay" — sum of all earning components BEFORE deductions.
   Do NOT use Net Pay or Take Home Pay.

RULES FOR monthly_take_home:
   Use "Net Pay" or "Take Home Pay" — the amount actually credited to the bank account.
"""
    })
    result, execution_time = converse(settings.bedrock_model_extract, content, PayslipData)
    logger.info("Raw LLM extraction",
            employer=result.employer,
            annual_ctc=result.annual_ctc,
            monthly_earnings=result.monthly_earnings,
            pay_period=result.pay_period)
    return result, execution_time



def _predict_justified_salary(
    payslip: PayslipData,
    expected_salary: float,
    verification: ExperienceVerification,
    company_segment: str = "MNC",
) -> tuple[SalaryAssessment, float]:
    """Predict justified salary based on current payslip, expected salary, verified experience, and company segment.

    Returns: (SalaryAssessment, analysis_time_seconds)
    """
    gap = expected_salary - payslip.annual_ctc
    gap_percentage = round((gap / payslip.annual_ctc) * 100, 1) if payslip.annual_ctc > 0 else 0

    # Segment-specific guidance: min % raise, max % raise, gap bridge %
    segment_config = {
        "STARTUP": (0.35, 0.50, 0.75),           # 35-50% raise, bridge 75% of gap
        "SCALE_UP": (0.20, 0.35, 0.70),          # 20-35% raise, bridge 70% of gap
        "TECH_MNC": (0.20, 0.30, 0.65),          # 20-30% raise, bridge 65% of gap
        "MNC": (0.15, 0.25, 0.50),               # 15-25% raise, bridge 50% of gap
        "ENTERPRISE": (0.10, 0.20, 0.40),        # 10-20% raise, bridge 40% of gap
    }
    min_raise, max_raise, gap_bridge = segment_config.get(company_segment, segment_config["MNC"])

    # Calculate justified salary using segment strategy
    raise_based_offer = payslip.annual_ctc * (1 + ((min_raise + max_raise) / 2))  # mid-point of range
    gap_based_offer = payslip.annual_ctc + (gap * gap_bridge)  # bridge X% of gap
    justified = max(raise_based_offer, gap_based_offer)  # pick the higher
    justified = min(justified, expected_salary)  # cap at expected (don't overshoot)

    prompt = f"""You are a senior HR compensation analyst. All figures are ANNUAL in {payslip.currency}.

CANDIDATE DATA:
- Current Annual CTC: {payslip.annual_ctc}
- Expected Annual CTC (recruiter benchmark): {expected_salary}
- Salary gap to close: {gap}
- Verified years of experience: {verification.extracted_years}
- Experience verdict: {verification.verdict}

HIRING COMPANY SEGMENT: {company_segment}
Target raise range: {min_raise*100:.0f}%-{max_raise*100:.0f}% above current
Target gap bridge: {gap_bridge*100:.0f}% of the gap

CALCULATION EXAMPLE:
If current={payslip.annual_ctc} and gap={gap}:
- Raise-based offer: {payslip.annual_ctc} × (1 + {(min_raise+max_raise)/2:.2f}) = {raise_based_offer:.0f}
- Gap-based offer: {payslip.annual_ctc} + ({gap} × {gap_bridge}) = {gap_based_offer:.0f}
- justified_salary should be: {justified:.0f}

INSTRUCTIONS:
- justified_salary: Use the calculated value above ({justified:.0f})
- Do NOT output 0 or leave blank
- rationale: 2 sentences explaining this offer vs current/expected
"""
    return converse(settings.bedrock_model_analyse, [{"text": prompt}], SalaryAssessment)


def assess(
    pdf_docs: list[bytes],
    expected_salary: float,
    verification: ExperienceVerification,
    company_segment: str = "MNC",
) -> tuple[PayslipData, SalaryAssessment]:
    """Extract payslip and generate salary assessment.

    Returns:
        (PayslipData, SalaryAssessment) - extracted data and assessment result
    """
    payslip, extraction_time = extract_payslip(pdf_docs)

    logger.info("Payslip extracted",
                employee=payslip.employee_name,
                monthly_earnings=payslip.monthly_earnings,
                annual_ctc=payslip.annual_ctc,
                currency=payslip.currency,
                extraction_time_seconds=round(extraction_time, 2))

    assessment, analysis_time = _predict_justified_salary(payslip, expected_salary, verification, company_segment)

    logger.info("Salary assessed",
                justified=assessment.justified_salary,
                current=assessment.current_salary,
                expected=assessment.expected_salary,
                analysis_time_seconds=round(analysis_time, 2))

    # Attach timing data to the assessment result
    assessment.extraction_time_seconds = round(extraction_time, 2)
    assessment.analysis_time_seconds = round(analysis_time, 2)

    return payslip, assessment


def predict_from_confirmed(
    current_salary: float,
    expected_salary: float,
    experience_years: float,
    currency: str = "INR",
    company_segment: str = "MNC",
) -> SalaryAssessment:
    """Run salary prediction using user-confirmed values instead of AI-extracted ones."""
    payslip = PayslipData(
        employer="",
        employee_name="",
        pay_period="",
        monthly_earnings=round(current_salary / 12, 2),
        annual_ctc=current_salary,
        currency=currency,
    )
    verification = ExperienceVerification(
        extracted_years=experience_years,
        expected_years=experience_years,
        verdict="MATCH",
        confidence=1.0,
        notes="User-confirmed values.",
    )
    assessment, analysis_time = _predict_justified_salary(payslip, expected_salary, verification, company_segment)
    assessment.analysis_time_seconds = round(analysis_time, 2)
    return assessment


def calculate_salary_trend(payslips: list[PayslipData]) -> RecentIncrement | None:
    """Calculate recent salary increment from multiple payslips.

    Args:
        payslips: List of PayslipData sorted by date (most recent first)

    Returns:
        RecentIncrement with detected status and details, or None if only 1 payslip
    """
    if len(payslips) < 2:
        return None

    most_recent = payslips[0]
    previous = payslips[1]  # Previous month

    increment_amount = most_recent.annual_ctc - previous.annual_ctc
    increment_percentage = round((increment_amount / previous.annual_ctc) * 100, 2) if previous.annual_ctc > 0 else 0.0

    detected = increment_amount > 0

    logger.info("Salary trend calculated",
                detected=detected,
                increment_amount=increment_amount,
                increment_percentage=increment_percentage,
                previous_salary=previous.annual_ctc,
                current_salary=most_recent.annual_ctc)

    return RecentIncrement(
        detected=detected,
        previous_salary=previous.annual_ctc if detected or increment_amount != 0 else None,
        increment_amount=increment_amount if detected or increment_amount != 0 else None,
        increment_percentage=increment_percentage if detected or increment_amount != 0 else None,
    )
