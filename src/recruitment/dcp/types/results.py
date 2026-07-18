from enum import Enum
from pydantic import BaseModel


class VerificationVerdict(str, Enum):
    MATCH = "MATCH"
    DISCREPANCY = "DISCREPANCY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class GapFlag(str, Enum):
    MATCH = "MATCH"  # Gap <= 3 months
    WARNING = "WARNING"  # Gap 3-6 months
    HIGH_DISCREPANCY = "HIGH_DISCREPANCY"  # Gap > 6 months


class RecentIncrement(BaseModel):
    detected: bool
    previous_salary: float | None = None  # Previous month salary
    increment_amount: float | None = None
    increment_percentage: float | None = None  # percentage


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
    justified_salary: float
    currency: str
    rationale: str
    recent_increment: RecentIncrement | None = None  # Salary trend across payslips
    extraction_time_seconds: float | None = None
    analysis_time_seconds: float | None = None
