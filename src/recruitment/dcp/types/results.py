from enum import Enum
from typing import Literal
from pydantic import BaseModel


class VerificationVerdict(str, Enum):
    MATCH = "MATCH"
    EXCEEDS_EXPECTATION = "EXCEEDS_EXPECTATION"   # candidate has more experience than required
    DISCREPANCY = "DISCREPANCY"                   # candidate is below expectation
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class GapFlag(str, Enum):
    MATCH = "MATCH"                        # within range or above expectation
    WARNING = "WARNING"                    # shortfall 3-6 months below expected
    HIGH_DISCREPANCY = "HIGH_DISCREPANCY"  # shortfall > 6 months below expected


class RecentIncrement(BaseModel):
    trend: Literal["RAISE", "DECREASE", "STABLE"]
    previous_salary: float | None = None
    change_amount: float | None = None
    change_percentage: float | None = None
    change_confidence: Literal["high", "medium", "low"] = "medium"


class ExperienceVerification(BaseModel):
    extracted_years: float
    expected_years: float
    verdict: VerificationVerdict
    discrepancy: float | None = None
    confidence: float
    notes: str
    gap_months: float = 0.0  # Experience gap in months (expected - extracted) * 12
    gap_flag: GapFlag = GapFlag.MATCH  # Flag if gap > 6 months
    llm_execution_time_seconds: float | None = None


class SalaryAssessment(BaseModel):
    current_salary: float
    expected_salary: float
    salary_gap: float | None = None        # expected - current; negative = candidate above benchmark
    above_benchmark: bool | None = None    # true when candidate earns more than the recruiter benchmark
    justified_salary: float
    currency: str
    rationale: str
    recent_increment: RecentIncrement | None = None
    analysis_time_seconds: float | None = None
