
from enum import Enum

class DocType(str, Enum):
    EXPERIENCE_LETTER="EXPERIENCE_LETTER"
    PAYSLIP="PAYSLIP"
    OTHER="OTHER"

class ProcessingStatus(str, Enum):
    UPLOADED = "UPLOADED"
    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    CATEGORIZED = "CATEGORIZED"
    ANALYZED = "ANALYZED"
    DONE = "DONE"
    FAILED = "FAILED"
