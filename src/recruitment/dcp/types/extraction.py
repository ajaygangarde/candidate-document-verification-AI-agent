from pydantic import BaseModel

class WorkRole(BaseModel):
    company: str
    title: str
    start: str | None = None
    end: str | None = None


class Experience(BaseModel):
    roles: list[WorkRole]
    total_years_experience: float


class PayslipData(BaseModel):
    employer: str
    employee_name: str
    pay_period: str
    monthly_earnings: float    # gross monthly earnings (before deductions)
    annual_ctc: float          # annual CTC — from Form 16 Gross Salary if present, else monthly_earnings × 12
    currency: str
    monthly_take_home: float | None = None
