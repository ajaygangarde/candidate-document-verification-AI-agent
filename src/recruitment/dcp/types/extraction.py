from typing import Literal
from pydantic import BaseModel


class WorkRole(BaseModel):
    company: str
    title: str
    start: str | None = None
    end: str | None = None


class Experience(BaseModel):
    roles: list[WorkRole] = []
    total_years_experience: float = 0.0


class AnnualSalary(BaseModel):
    value: float
    source: Literal["annual_ctc", "estimated_from_monthly", "form_16"]
    confidence: Literal["high", "medium", "low"]
    human_review_required: bool = False
    review_reason: str | None = None


class PayslipData(BaseModel):
    employer: str = ""
    employee_name: str = ""
    pay_period: str = ""
    monthly_earnings: float
    monthly_deductions: float | None = None   # PF + TDS + Prof Tax + other deductions
    monthly_take_home: float | None = None    # net — amount credited to bank
    annual_ctc: float | None = None   # set ONLY when an explicit annual section is found
    annual_salary: AnnualSalary | None = None  # populated after Step 2-3 validation
    currency: str = "INR"
