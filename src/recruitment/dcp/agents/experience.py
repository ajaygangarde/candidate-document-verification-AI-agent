from datetime import date, datetime
from recruitment.shared.config import settings
from recruitment.shared.services.llm import converse
from recruitment.dcp.types.extraction import Experience, WorkRole
from recruitment.dcp.types.results import ExperienceVerification, VerificationVerdict, GapFlag
from recruitment.shared.logging import logger

def _parse_date(value: str | None) -> date | None:
    """Parse a date the model may return as YYYY-MM-DD, YYYY-MM, or YYYY."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    logger.warning("Unparseable role date", value=value)
    return None

def _years_from_role(role: WorkRole) -> float:
    start = _parse_date(role.start)
    end = _parse_date(role.end) or date.today()
    if start is None:
        return 0.0
    return round((end - start).days / 365.25, 1)

def _compute_total_years(experience: Experience) -> float:
    return round(sum(_years_from_role(r) for r in experience.roles), 1)

def _extract_experience(text: list[str]) -> tuple[Experience, float]:
    """Extract work experience from documents.

    Returns: (Experience, extraction_time_seconds)
    """
    combined = "\n\n---\n\n".join(text)
    prompt = f"""Extract all work experience from the documents below.

For each role provide: company name, job title, start date (YYYY-MM format), end date (YYYY-MM or null if current).

Then calculate total_years_experience by summing the duration of each role in years.
Example: start=2019-06, end=2022-06 = 3.0 years. If end is null, use today's date.
Round to one decimal place. Do NOT leave total_years_experience as 0 if dates are present.

Documents:
{combined[:12000]}
"""
    return converse(settings.bedrock_model_extract, [{"text": prompt}], Experience)

def _compute_verdict(extracted: float, expected: float) -> tuple[VerificationVerdict, float | None]:
    surplus = round(extracted - expected, 1)  # positive = candidate exceeds, negative = shortfall
    if extracted == 0:
        return VerificationVerdict.INSUFFICIENT_DATA, None
    if surplus >= -0.5 and surplus <= 0.5:
        return VerificationVerdict.MATCH, None
    if surplus > 0.5:
        return VerificationVerdict.EXCEEDS_EXPECTATION, None
    return VerificationVerdict.DISCREPANCY, abs(surplus)  # discrepancy only on shortfall

def verify(text: list[str], expected_years: float) -> ExperienceVerification:
    experience, extraction_time = _extract_experience(text)
    total_years = _compute_total_years(experience)
    verdict, discrepancy = _compute_verdict(total_years, expected_years)

    # gap_months: positive = candidate exceeds expectation, negative = shortfall
    gap_months = round((total_years - expected_years) * 12, 1)

    # gap_flag only fires when candidate is below expectation
    shortfall_months = -gap_months  # positive when candidate is short
    if shortfall_months > 6:
        gap_flag = GapFlag.HIGH_DISCREPANCY
    elif shortfall_months > 3:
        gap_flag = GapFlag.WARNING
    else:
        gap_flag = GapFlag.MATCH

    if verdict == VerificationVerdict.EXCEEDS_EXPECTATION:
        notes = f"Candidate exceeds expectation by {round(total_years - expected_years, 1)} yrs ({len(experience.roles)} role(s) found)."
    elif verdict == VerificationVerdict.DISCREPANCY:
        notes = f"Candidate is {round(expected_years - total_years, 1)} yrs short of expectation ({len(experience.roles)} role(s) found)."
    elif verdict == VerificationVerdict.INSUFFICIENT_DATA:
        notes = "Could not extract experience from documents."
    else:
        notes = f"Found {len(experience.roles)} role(s). Total: {total_years} yrs matches expected {expected_years} yrs."

    logger.info("Experience verified",
                verdict=verdict,
                extracted=total_years,
                expected=expected_years,
                gap_months=gap_months,
                gap_flag=gap_flag,
                extraction_time_seconds=round(extraction_time, 2))

    return ExperienceVerification(
        extracted_years=total_years,
        expected_years=expected_years,
        verdict=verdict,
        discrepancy=discrepancy,
        confidence=0.9 if verdict != VerificationVerdict.INSUFFICIENT_DATA else 0.2,
        notes=notes,
        gap_months=gap_months,
        gap_flag=gap_flag,
        llm_execution_time_seconds=round(extraction_time, 2),
    )