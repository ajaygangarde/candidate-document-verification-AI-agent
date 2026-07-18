import json
import psycopg
from recruitment.shared.config import settings
from recruitment.shared.logging import logger


def _conn():
    return psycopg.connect(settings.database_url)


def create_candidate_verification(
    candidate_id: str,
    candidate_name: str,
    expected_experience_years: float,
    expected_salary: float,
    currency: str = "INR",
) -> str:
    with _conn() as conn:
        row = conn.execute(
            """
            INSERT INTO candidate_verifications
                (candidate_id, candidate_name, expected_experience_years, expected_salary, currency, status)
            VALUES (%s, %s, %s, %s, %s, 'PENDING')
            RETURNING verification_id
            """,
            (candidate_id, candidate_name, expected_experience_years, expected_salary, currency),
        ).fetchone()
        logger.info("Created verification", verification_id=str(row[0]), candidate_id=candidate_id)
        return str(row[0])


def get_candidate_verification(verification_id: str) -> dict:
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT verification_id, candidate_id, candidate_name,
                   expected_experience_years, expected_salary, currency,
                   status, experience_verification, salary_assessment, summary, created_at
            FROM candidate_verifications
            WHERE verification_id = %s
            """,
            (verification_id,),
        ).fetchone()
        if row is None:
            return {"error": "not found"}
        return {
            "verification_id": str(row[0]),
            "candidate_id": row[1],
            "candidate_name": row[2],
            "expected_experience_years": row[3],
            "expected_salary": row[4],
            "currency": row[5],
            "status": row[6],
            "experience_verification": row[7],
            "salary_assessment": row[8],
            "summary": row[9],
            "created_at": row[10].isoformat(),
        }


def save_document_keys(verification_id: str, keys: list[str]) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE candidate_verifications SET document_keys = %s WHERE verification_id = %s",
            (json.dumps(keys), verification_id),
        )
        logger.info("Document keys saved", verification_id=verification_id, count=len(keys))


def get_candidate(verification_id: str) -> dict:
    # TODO: in production, fetch from candidates/resumes table using candidate_id
    # These are the recruiter's expectations the candidate provided at application time
    return {
        "candidate_id": "candidate-001",
        "company_segment": "TECH_MNC",  # STARTUP | SCALE_UP | MNC | ENTERPRISE
        "expected_experience_years": 7,
        "expected_salary": 3500000.0,
        "currency": "INR",
    }


def save_results(
    verification_id: str,
    verification: dict,
    assessment: dict,
    summary: str = None,
) -> None:
    with _conn() as conn:
        conn.execute(
            """
            UPDATE candidate_verifications
            SET experience_verification = %s,
                salary_assessment = %s,
                summary = %s
            WHERE verification_id = %s
            """,
            (json.dumps(verification), json.dumps(assessment), summary, verification_id),
        )
        logger.info("Results saved", verification_id=verification_id)


def update_verification_status(verification_id: str, status: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE candidate_verifications SET status = %s WHERE verification_id = %s",
            (status, verification_id),
        )
        logger.info("Status updated", verification_id=verification_id, status=status)


def save_confirmed_categories(verification_id: str, confirmed_docs: list[dict]) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE candidate_verifications SET confirmed_categories = %s WHERE verification_id = %s",
            (json.dumps(confirmed_docs), verification_id),
        )
        logger.info("Confirmed categories saved", verification_id=verification_id, count=len(confirmed_docs))


def get_confirmed_categories(verification_id: str) -> list[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT confirmed_categories FROM candidate_verifications WHERE verification_id = %s",
            (verification_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return []
        return row[0]
