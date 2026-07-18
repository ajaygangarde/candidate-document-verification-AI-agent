from recruitment.shared.config import settings
from recruitment.shared.services.llm import converse
from recruitment.dcp.types.extraction import PayslipData, AnnualSalary
from recruitment.dcp.types.results import SalaryAssessment, ExperienceVerification, RecentIncrement
from recruitment.shared.logging import logger


# ── Step 2-3: Validate and ground annual salary value ──────────────────────

def _build_annual_salary(payslip: PayslipData) -> AnnualSalary:
    """Validate extracted values and produce a grounded AnnualSalary with source + confidence.

    Step 2 — Validate gross > net (2% tolerance for minimal-deduction edge cases).
    Step 3 — Select annual value: use extracted annual_ctc if present and consistent, else estimate.
    """
    estimated = round(payslip.monthly_earnings * 12, 2)

    # Step 2: gross must exceed net pay
    if payslip.monthly_take_home and payslip.monthly_earnings < payslip.monthly_take_home * 1.02:
        logger.warning("Gross earnings not greater than net pay — flagging for human review",
                       monthly_earnings=payslip.monthly_earnings,
                       monthly_take_home=payslip.monthly_take_home)
        return AnnualSalary(
            value=estimated,
            source="estimated_from_monthly",
            confidence="low",
            human_review_required=True,
            review_reason="Gross earnings should be greater than net pay — possible extraction swap.",
        )

    # Step 3: annual value selection
    if payslip.annual_ctc and payslip.annual_ctc > 0:
        ratio = payslip.annual_ctc / estimated if estimated > 0 else 0
        if 0.85 <= ratio <= 1.30:
            # annual_ctc is consistent with monthly — grounded to annual section
            return AnnualSalary(
                value=payslip.annual_ctc,
                source="annual_ctc",
                confidence="high",
            )
        else:
            # annual_ctc diverges significantly from monthly × 12 — extraction noise
            logger.warning("Extracted annual_ctc diverges from monthly estimate — using monthly × 12",
                           annual_ctc=payslip.annual_ctc,
                           monthly_estimate=estimated,
                           ratio=round(ratio, 2))
            return AnnualSalary(
                value=estimated,
                source="estimated_from_monthly",
                confidence="medium",
                review_reason=f"Extracted annual_ctc ({payslip.annual_ctc:,.0f}) diverges from monthly estimate ({estimated:,.0f}) — using monthly × 12.",
            )

    # No annual section found in document — estimate from monthly
    return AnnualSalary(
        value=estimated,
        source="estimated_from_monthly",
        confidence="medium",
    )


# ── Extraction ──────────────────────────────────────────────────────────────

def extract_payslip(pdf_docs: list[bytes]) -> tuple[PayslipData, float]:
    """Send raw PDF bytes to the LLM via Converse, then validate and ground the annual salary.

    Returns: (PayslipData with annual_salary populated, extraction_time_seconds)
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

Extract these fields for every payslip:
- employer: company name
- employee_name: employee full name
- pay_period: month/period of this payslip (e.g. "2025-12")
- currency: currency code (e.g. INR, USD)
- monthly_earnings: gross pay BEFORE deductions (see rules below)
- monthly_deductions: total deductions (see rules below)
- monthly_take_home: net pay credited to bank (see rules below)
- annual_ctc: only when an explicit annual section exists (see rules below)

RULES FOR monthly_earnings:
   Use "Total Earnings" or "Gross Pay" — sum of all earning components BEFORE deductions.
   Do NOT use Net Pay or Take Home Pay.

RULES FOR monthly_deductions:
   Sum of ALL deductions: PF (employee contribution) + TDS + Professional Tax + any others.
   This is the total subtracted from gross to arrive at net pay.

RULES FOR monthly_take_home:
   Use "Net Pay" or "Take Home Pay" — amount actually credited to the bank account.

RULES FOR annual_ctc — set ONLY when an explicit annual section is present:
   1. Annual Summary / Form 16 Summary / Income Tax Summary section:
      Use "Gross Salary" or "Total Compensation" from that section.
   2. Income Tax Calculation section with an Annual / Projected Annual column:
      Use the "Total" or "Annual Total" row value.
   3. "CTC Monthly" or "Monthly CTC" field explicitly shown:
      Multiply by 12.
   If NONE of the above apply, leave annual_ctc as null.
   Do NOT compute annual_ctc yourself by multiplying monthly earnings.
"""
    })
    result, execution_time = converse(settings.bedrock_model_extract, content, PayslipData)

    # Steps 2-3: validate and ground the annual salary
    result.annual_salary = _build_annual_salary(result)

    logger.info("Payslip extracted and grounded",
                employer=result.employer,
                annual_ctc_raw=result.annual_ctc,
                annual_salary_value=result.annual_salary.value,
                annual_salary_source=result.annual_salary.source,
                annual_salary_confidence=result.annual_salary.confidence,
                human_review_required=result.annual_salary.human_review_required,
                monthly_earnings=result.monthly_earnings,
                pay_period=result.pay_period)
    return result, execution_time


# ── Salary trend detection ──────────────────────────────────────────────────

def calculate_salary_trend(payslips: list[PayslipData]) -> RecentIncrement | None:
    """Detect salary change across payslips using grounded annual values and tolerance bands.

    Tolerance bands (on monthly earnings to avoid annual projection noise):
      < 5%   — within payroll noise (LWP, arrears, bonuses) → STABLE
      5–15%  — possible change → medium confidence
      > 15%  — likely salary revision → high confidence
    """
    if len(payslips) < 2:
        return None

    def _annual_value(p: PayslipData) -> tuple[float, str]:
        if p.annual_salary:
            return p.annual_salary.value, p.annual_salary.source
        return round(p.monthly_earnings * 12, 2), "estimated_from_monthly"

    recent_val, recent_source = _annual_value(payslips[0])
    prev_val, prev_source = _annual_value(payslips[1])

    change_amount = round(recent_val - prev_val, 2)
    change_pct = round((change_amount / prev_val) * 100, 2) if prev_val > 0 else 0.0
    abs_pct = abs(change_pct)

    # Tolerance bands
    if abs_pct < 5:
        trend = "STABLE"
        confidence = "low"
    elif abs_pct < 15:
        trend = "RAISE" if change_amount > 0 else "DECREASE"
        confidence = "medium"
    else:
        trend = "RAISE" if change_amount > 0 else "DECREASE"
        confidence = "high"

    # Mixing different source types (one from annual section, one estimated) reduces reliability
    if recent_source != prev_source:
        confidence = "low"

    logger.info("Salary trend calculated",
                trend=trend,
                change_amount=change_amount,
                change_percentage=change_pct,
                change_confidence=confidence,
                recent_source=recent_source,
                prev_source=prev_source)

    return RecentIncrement(
        trend=trend,
        previous_salary=prev_val,
        change_amount=change_amount,
        change_percentage=change_pct,
        change_confidence=confidence,
    )


# ── Salary assessment ───────────────────────────────────────────────────────

def _get_annual_ctc(payslip: PayslipData) -> float:
    """Return the best available annual CTC — grounded value takes priority."""
    if payslip.annual_salary:
        return payslip.annual_salary.value
    if payslip.annual_ctc:
        return payslip.annual_ctc
    return round(payslip.monthly_earnings * 12, 2)


def _predict_justified_salary(
    payslip: PayslipData,
    expected_salary: float,
    verification: ExperienceVerification,
    company_segment: str = "MNC",
) -> tuple[SalaryAssessment, float]:
    """Predict justified salary using the grounded annual CTC value."""
    current_ctc = _get_annual_ctc(payslip)
    gap = expected_salary - current_ctc
    gap_percentage = round((gap / current_ctc) * 100, 1) if current_ctc > 0 else 0

    segment_config = {
        "STARTUP":    (0.35, 0.50, 0.75),
        "SCALE_UP":   (0.20, 0.35, 0.70),
        "TECH_MNC":   (0.20, 0.30, 0.65),
        "MNC":        (0.15, 0.25, 0.50),
        "ENTERPRISE": (0.10, 0.20, 0.40),
    }
    min_raise, max_raise, gap_bridge = segment_config.get(company_segment, segment_config["MNC"])

    raise_based_offer = current_ctc * (1 + ((min_raise + max_raise) / 2))
    gap_based_offer = current_ctc + (gap * gap_bridge)
    justified = max(raise_based_offer, gap_based_offer)
    justified = min(justified, expected_salary)

    prompt = f"""You are a senior HR compensation analyst. All figures are ANNUAL in {payslip.currency}.

CANDIDATE DATA:
- Current Annual CTC: {current_ctc}
- Expected Annual CTC (recruiter benchmark): {expected_salary}
- Salary gap to close: {gap}
- Verified years of experience: {verification.extracted_years}
- Experience verdict: {verification.verdict}

HIRING COMPANY SEGMENT: {company_segment}
Target raise range: {min_raise*100:.0f}%-{max_raise*100:.0f}% above current
Target gap bridge: {gap_bridge*100:.0f}% of the gap

CALCULATION:
- Raise-based offer: {current_ctc} × (1 + {(min_raise+max_raise)/2:.2f}) = {raise_based_offer:.0f}
- Gap-based offer: {current_ctc} + ({gap} × {gap_bridge}) = {gap_based_offer:.0f}
- justified_salary: {justified:.0f}

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
    payslip, extraction_time = extract_payslip(pdf_docs)

    logger.info("Payslip extracted",
                employee=payslip.employee_name,
                monthly_earnings=payslip.monthly_earnings,
                annual_salary=payslip.annual_salary.value if payslip.annual_salary else None,
                currency=payslip.currency,
                extraction_time_seconds=round(extraction_time, 2))

    assessment, analysis_time = _predict_justified_salary(payslip, expected_salary, verification, company_segment)

    logger.info("Salary assessed",
                justified=assessment.justified_salary,
                current=assessment.current_salary,
                expected=assessment.expected_salary,
                analysis_time_seconds=round(analysis_time, 2))

    assessment.analysis_time_seconds = round(analysis_time, 2)
    return payslip, assessment


def predict_from_confirmed(
    current_salary: float,
    expected_salary: float,
    experience_years: float,
    currency: str = "INR",
    company_segment: str = "MNC",
) -> SalaryAssessment:
    """Run salary prediction using user-confirmed values — always high confidence."""
    payslip = PayslipData(
        employer="",
        employee_name="",
        pay_period="",
        monthly_earnings=round(current_salary / 12, 2),
        annual_ctc=current_salary,
        annual_salary=AnnualSalary(
            value=current_salary,
            source="annual_ctc",
            confidence="high",
        ),
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
