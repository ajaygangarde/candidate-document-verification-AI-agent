from pydantic import BaseModel
from recruitment.shared.services.llm import converse
from recruitment.dcp.types.documents import DocType
from recruitment.shared.logging import logger
from recruitment.shared.config import settings
class DocCategory(BaseModel):
    doc_type: DocType
    reasoning: str

def categorize(text) -> tuple[DocType, float]:
    """Categorize a document into EXPERIENCE_LETTER, PAYSLIP, or OTHER.

    Returns: (DocType, categorization_time_seconds)
    """
    prompt = f""" You are an HR document classification expert
    Classify the document into exactly one of these categories:

    2. EXPERIENCE_LETTER
    - A document issued by an employer confirming a person's employment.
    - Typically includes employee name, designation, employment period (joining and relieving dates), and phrases like "This is to certify that" or "worked with our organization".

    3. PAYSLIP
    - A monthly salary document.
    - Typically contains salary details such as Gross Salary, Net Salary, Earnings, Deductions, PF, Tax, or Pay Period.

    If the document does not clearly match any of the above, return OTHER.

    Document text:
    {text[:1000]}

    Return only one of:
    EXPERIENCE_LETTER
    PAYSLIP
    OTHER
    """

    result, categorization_time = converse(settings.bedrock_model_categorise, [{"text": prompt}], DocCategory)
    logger.info("document_categorized",
                doc_type=result.doc_type,
                reasoning=result.reasoning,
                categorization_time_seconds=round(categorization_time, 2))
    return result.doc_type, categorization_time