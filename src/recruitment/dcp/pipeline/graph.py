from langgraph.graph import StateGraph, START, END

from recruitment.dcp.pipeline.state import PipelineState
from recruitment.shared.services.storage import get_file_bytes
from recruitment.shared.services.text_extractor import extract_text, extract_payslip_bytes
from recruitment.shared.services.database import save_results, update_verification_status
from recruitment.dcp.types.documents import DocType
from recruitment.dcp.types.results import ExperienceVerification, VerificationVerdict, GapFlag
from recruitment.dcp.types.extraction import PayslipData
from recruitment.dcp.agents.experience import verify
from recruitment.dcp.agents.payslip import extract_payslip, _predict_justified_salary, calculate_salary_trend
from recruitment.shared.logging import logger


# ── Node 1 ─────────────────────────────────────────────────────────────────
# Downloads each doc, extracts text, splits by confirmed doc_type.
# Runs once before the parallel split.

def load_docs_node(state: PipelineState) -> dict:
    experience_texts = []
    payslip_results = []

    for doc in state["confirmed_docs"]:
        file_bytes = get_file_bytes(doc["s3_key"])
        text, _ = extract_text(file_bytes)

        if doc["doc_type"] == DocType.EXPERIENCE_LETTER:
            experience_texts.append(text)
        elif doc["doc_type"] == DocType.PAYSLIP:
            payslip_results.append({
                "s3_key": doc["s3_key"],
                "pdf_bytes": extract_payslip_bytes(file_bytes),
            })

    logger.info("Docs loaded",
                experience_count=len(experience_texts),
                payslip_count=len(payslip_results))

    return {
        "experience_texts": experience_texts,
        "payslip_results": payslip_results,
    }


# ── Node 2 ─────────────────────────────────────────────────────────────────
# Calls the experience agent with all experience texts.
# Runs in PARALLEL with payslip_extract_node.

def experience_node(state: PipelineState) -> dict:
    if not state["experience_texts"]:
        logger.info("No experience documents — skipping experience agent")
        return {"experience_result": {}}

    result = verify(
        text=state["experience_texts"],
        expected_years=state["candidate"]["expected_experience_years"],
    )
    return {"experience_result": result.model_dump()}


# ── Node 3 ─────────────────────────────────────────────────────────────────
# Extracts PayslipData from each PDF via Bedrock Converse.
# Runs in PARALLEL with experience_node — no dependency between them.

def payslip_extract_node(state: PipelineState) -> dict:
    payslip_docs = state["payslip_results"]

    if not payslip_docs:
        logger.info("No payslip documents — skipping payslip extraction")
        return {"payslip_extractions": []}

    extractions = []
    for doc in payslip_docs:
        payslip_data, extraction_time = extract_payslip([doc["pdf_bytes"]])
        logger.info("Payslip extracted",
                    s3_key=doc["s3_key"],
                    pay_period=payslip_data.pay_period,
                    annual_salary_value=payslip_data.annual_salary.value if payslip_data.annual_salary else None,
                    annual_salary_source=payslip_data.annual_salary.source if payslip_data.annual_salary else None,
                    annual_salary_confidence=payslip_data.annual_salary.confidence if payslip_data.annual_salary else None,
                    human_review_required=payslip_data.annual_salary.human_review_required if payslip_data.annual_salary else False,
                    extraction_time_seconds=round(extraction_time, 2))
        extractions.append(payslip_data.model_dump())

    return {"payslip_extractions": extractions}


# ── Node 4 ─────────────────────────────────────────────────────────────────
# Runs salary assessment using BOTH experience result and extracted payslips.
# Runs AFTER both parallel nodes complete — fan-in point.

def payslip_assess_node(state: PipelineState) -> dict:
    extractions = state.get("payslip_extractions") or []

    if not extractions:
        logger.info("No payslip extractions — skipping salary assessment")
        return {"salary_assessment": {}}

    candidate = state["candidate"]
    experience_result = state.get("experience_result") or {}

    # Build ExperienceVerification from experience_node result
    verification = ExperienceVerification(**experience_result) if experience_result else ExperienceVerification(
        extracted_years=candidate["expected_experience_years"],
        expected_years=candidate["expected_experience_years"],
        verdict=VerificationVerdict.MATCH,
        confidence=0.5,
        notes="No experience documents provided.",
        gap_months=0.0,
        gap_flag=GapFlag.MATCH,
    )

    # Rebuild PayslipData objects and sort by pay_period descending
    payslips = [PayslipData(**e) for e in extractions]
    payslips.sort(key=lambda p: p.pay_period or "", reverse=True)

    most_recent = payslips[0]
    assessment, analysis_time = _predict_justified_salary(
        payslip=most_recent,
        expected_salary=candidate["expected_salary"],
        verification=verification,
        company_segment=candidate.get("company_segment", "MNC"),
    )
    assessment.analysis_time_seconds = round(analysis_time, 2)
    assessment.salary_gap = round(candidate["expected_salary"] - assessment.current_salary, 2)
    assessment.above_benchmark = assessment.current_salary > candidate["expected_salary"]

    # Salary trend across multiple payslips
    if len(payslips) > 1:
        trend = calculate_salary_trend(payslips)
        if trend:
            assessment.recent_increment = trend

    annual_salary = most_recent.annual_salary
    logger.info("Salary assessed",
                justified=assessment.justified_salary,
                current=assessment.current_salary,
                expected=assessment.expected_salary,
                ctc_source=annual_salary.source if annual_salary else "unknown",
                ctc_confidence=annual_salary.confidence if annual_salary else "unknown",
                human_review_required=annual_salary.human_review_required if annual_salary else False)

    return {"salary_assessment": assessment.model_dump()}


# ── Node 5 ─────────────────────────────────────────────────────────────────
# Persists results to DB and marks verification DONE.

def persist_node(state: PipelineState) -> dict:
    save_results(
        state["verification_id"],
        state["experience_result"],
        state["salary_assessment"],
    )
    update_verification_status(state["verification_id"], "DONE")
    logger.info("Verification complete", verification_id=state["verification_id"])
    return {}


# ── Graph wiring ────────────────────────────────────────────────────────────
#
#   START
#     ↓
#   load_docs_node
#     ↓                 ↓
#   experience_node   payslip_extract_node   ← parallel fan-out
#     ↓                 ↓
#       payslip_assess_node                  ← fan-in (waits for both)
#             ↓
#         persist_node
#             ↓
#            END

def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("load_docs", load_docs_node)
    graph.add_node("experience", experience_node)
    graph.add_node("payslip_extract", payslip_extract_node)
    graph.add_node("payslip_assess", payslip_assess_node)
    graph.add_node("persist", persist_node)

    graph.add_edge(START, "load_docs")

    # Fan-out: both run in parallel after load_docs
    graph.add_edge("load_docs", "experience")
    graph.add_edge("load_docs", "payslip_extract")

    # Fan-in: payslip_assess waits for both to complete
    graph.add_edge("experience", "payslip_assess")
    graph.add_edge("payslip_extract", "payslip_assess")

    graph.add_edge("payslip_assess", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


pipeline = build_graph()
