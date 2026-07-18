from typing_extensions import TypedDict


class DocInput(TypedDict):
    s3_key: str
    doc_type: str


class PipelineState(TypedDict):
    # ── set once at the start ──────────────────────────────
    verification_id: str
    candidate: dict
    confirmed_docs: list[DocInput]

    # ── written by load_docs_node ──────────────────────────
    experience_texts: list[str]
    payslip_results: list[dict]        # raw pdf_bytes per payslip

    # ── written by parallel nodes ──────────────────────────
    experience_result: dict            # written by experience_node
    payslip_extractions: list[dict]    # written by payslip_extract_node

    # ── written by payslip_assess_node ─────────────────────
    salary_assessment: dict
