# AI Recruitment OS — MVP Build Plan (Multi-Agent Document Pipeline)

## Context

Greenfield build (`recruiter_AI_candidate_document_analysis_tool/` is currently empty).

We are building an **event-driven, multi-agent document-processing pipeline** for
recruitment. A candidate uploads a batch of documents (resume + payslips); the pipeline
extracts text, categorizes each document, and runs specialized agents that reconcile the
**document evidence against the candidate's expected values already stored in PostgreSQL**
(the recruiter's/ATS source of truth). Results are written back to Postgres for a React UI
to fetch later.

Architecture philosophy (validated as good for 2026): **ports & adapters / "functional
core, imperative shell."** All business logic lives in a reusable Python pipeline; AWS
Lambda is only a thin wrapper. **One codebase** serves local development (`python main.py`
against *real* AWS — no Lambda, no SAM Local, no Docker, no mocks) and production
(SAM/CloudFormation). Locally, `main.py` simulates the S3 ObjectCreated event by invoking
the same LangGraph core against real S3/Textract/Bedrock/Postgres.

## How we'll work (LEARNING MODE — important)

This project is being built to **learn Python and a best-practice development workflow**.
Therefore we do **not** mass-generate the codebase. We go **one step at a time**:

1. I explain the concept and *why* it's the best-practice choice (the "why" matters more
   than the code here).
2. I show only the focused snippet for that single step.
3. **The user types the code themselves** — I do not auto-write whole files.
4. We run/verify that step against real AWS or locally before moving on.
5. Then we proceed to the next step.

My role is **guide + reviewer**, not autocomplete. Keep each step small, explain trade-offs,
and pause for the user to implement and ask questions. The step list in "Implementation
Steps" below is the ordered curriculum — we walk it sequentially.

**First action on approval:** copy this plan to `PLAN.md` in the project root
(`recruiter_AI_candidate_document_analysis_tool/PLAN.md`) so it lives with the code.

### Target architecture
```
React Frontend  →  API Gateway + Upload Lambda  →  presigned PUT URLs
       →  Browser uploads to S3  →  S3 ObjectCreated event
       →  Processing Lambda (Python + LangGraph)
              1. Load candidate record from Postgres + download docs from S3
              2. Text Extraction  (tiered: PyMuPDF native → Textract OCR fallback)
              3. Document Categorisation (LLM router → resume / payslip / other)
              4. Agent fan-out:
                   • Experience Verification Agent
                   • Payslip Agent (salary)
              5. Structured JSON results
              6. Persist to Postgres + update submission status
       →  PostgreSQL  →  React UI fetches analysis result
```

### Confirmed scope & decisions
- **MVP features:** (1) Document Text Extraction, (2) Document Categorisation,
  (3) Experience Verification Agent, (4) Payslip Agent. *Out of scope for now:* candidate
  matching, fraud detection, recommendation, resume scoring.
- **Extraction:** Tiered — native PDF text (PyMuPDF) first, **Textract async OCR only as
  fallback** for scanned/image docs (payslips are often scanned → fallback matters).
- **Orchestration:** Event-driven / staged. Independently-invokable stages + a status
  state machine in Postgres. `main.py` drives stages locally; S3/SNS events drive prod.
- **Processing unit:** **Candidate submission (batch)** — many docs per candidate,
  cross-document agents run over the whole submission.
- **Frontend:** Backend pipeline first. Upload/Results API handlers authored now; React UI
  deferred to a later phase.

### Agent semantics (confirmed)
- **Experience Verification Agent:** extract work history / total experience from the
  resume, compare against the candidate's **expected experience stored in the DB**, and
  emit a verification result (verified years, match/discrepancy, confidence, notes).
- **Payslip Agent:** extract **current salary** from the payslip, compare against the
  candidate's **expected salary stored in the DB**, and **predict a justified salary**
  for the candidate (with reasoning, informed by verified experience).

### 2026 best practices baked in
- Textract is a **fallback tier**, not the default; multi-page/scanned OCR uses **async
  Textract** (`StartDocumentAnalysis` + poll locally / SNS in prod).
- All LLM extraction is **schema-enforced** via Bedrock tool-use + Pydantic (no
  prompt-and-pray). Categorization returns a constrained enum.
- **Status state machine** per submission + per document → idempotent, re-runnable.
- PII from day one: S3 SSE-KMS, presigned uploads, least-privilege IAM, encrypted Postgres.
- Bedrock model id is **configurable**; default to the latest capable Claude on Bedrock via
  a cross-region inference profile (verify region availability at build time).

---

## Project Structure

Folder naming follows Node/TypeScript conventions (familiar to the team):
- `services/`     → external integrations (S3, Textract, Bedrock, DB) — was `adapters/`
- `controllers/`  → HTTP/Lambda entrypoints — was `handlers/`
- `types/`        → Pydantic schemas / data shapes — was `models/`
- `agents/`       → AI agents (unchanged)
- `pipeline/`     → LangGraph orchestration (unchanged)

```
recruiter_AI_candidate_document_analysis_tool/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── main.py                       # LOCAL driver: simulate S3 event → run graph vs real AWS
├── seed_candidates.py            # dev: seed candidate records (expected exp + salary)
├── alembic.ini
├── migrations/versions/
├── infra/
│   └── template.yaml             # SAM/CloudFormation (authored now, deployed later)
├── src/recruitment/
│   ├── config.py                 # pydantic-settings (region, bucket, db, model id, sns…)
│   ├── logging.py                # structured logging (aws-lambda-powertools; local too)
│   ├── models/
│   │   ├── candidate.py          # Candidate (expected_experience, expected_salary…)
│   │   ├── documents.py          # DocType enum, ProcessingStatus enum, domain types
│   │   ├── extraction.py         # ResumeExperience, PayslipData Pydantic (extract targets)
│   │   ├── results.py            # ExperienceVerification, SalaryAssessment Pydantic
│   │   └── db.py                 # SQLAlchemy ORM models
│   ├── adapters/
│   │   ├── storage.py            # S3: presigned PUT, get_bytes, SSE-KMS
│   │   ├── text_extract.py       # PyMuPDF native text + needs_ocr() heuristic
│   │   ├── ocr.py                # Textract async start/poll/parse
│   │   ├── llm.py                # Bedrock (langchain-aws) structured tool-use helpers
│   │   └── repository.py         # Postgres: candidate read, status, persist results
│   ├── agents/
│   │   ├── categorizer.py        # classify doc → DocType (constrained)
│   │   ├── experience_agent.py   # resume experience vs DB expected → verification
│   │   └── payslip_agent.py      # payslip salary vs DB expected → justified salary
│   ├── pipeline/
│   │   ├── state.py              # PipelineState (submission, candidate, docs, results)
│   │   ├── stages.py             # ingest / extract / categorize / verify / assess / persist
│   │   └── graph.py              # LangGraph wiring (router + fan-out + aggregate)
│   └── handlers/
│       ├── upload_handler.py     # API GW: create submission + return presigned URLs
│       ├── process_handler.py    # S3 event → run the LangGraph core
│       └── results_handler.py    # API GW: fetch submission results (for React later)
└── tests/
    ├── test_schemas.py
    └── test_pipeline_smoke.py
```

---

## Implementation Steps

### 1. Scaffold + config
- `pyproject.toml`: `boto3`, `pydantic`, `pydantic-settings`, `python-dotenv`, `PyMuPDF`,
  `sqlalchemy`, `psycopg[binary]`, `alembic`, `langgraph`, `langchain-aws`,
  `aws-lambda-powertools`.
- `config.py` `Settings`: `AWS_REGION`, `S3_BUCKET`, `KMS_KEY_ID`, `DATABASE_URL`,
  `BEDROCK_MODEL_ID`, `TEXTRACT_SNS_TOPIC_ARN`, `TEXTRACT_ROLE_ARN`. `.env.example` +
  `logging.py` (Powertools `Logger`).

### 2. Database layer + state machine
- `models/documents.py`: `DocType` = `RESUME | PAYSLIP | OTHER`; `ProcessingStatus` =
  `UPLOADED → TEXT_EXTRACTED → CATEGORIZED → ANALYZED → DONE` (+ `FAILED`).
- `models/db.py` tables:
  - `candidates` — id, name, **expected_experience_years**, expected role/details,
    **expected_salary**, currency (the recruiter's source-of-truth expectations).
  - `submissions` — id, candidate_id FK, status, timestamps.
  - `documents` — id, submission_id FK, s3_key, filename, doc_type, ocr_method, raw_text,
    status, error.
  - `experience_verifications` — submission FK, extracted_years, verified (bool/enum),
    discrepancy, confidence, notes (JSONB detail).
  - `salary_assessments` — submission FK, current_salary, expected_salary,
    **justified_salary**, currency, rationale (JSONB).
- `repository.py`: `get_candidate`, `create_submission`, `add_document`, status setters,
  `save_raw_text`, `save_experience_verification`, `save_salary_assessment` (each write
  advances status; idempotent re-runs).
- Alembic migration creating all tables. `seed_candidates.py` to insert dev candidate rows.

### 3. Pydantic schemas (extraction + result targets)
- `extraction.py`: `ResumeExperience` (roles[{company,title,start,end}],
  total_years_experience); `PayslipData` (employer, employee_name, pay_period,
  current_salary, currency, net/gross).
- `results.py`: `ExperienceVerification` (extracted_years, expected_years, verdict,
  discrepancy, confidence, notes); `SalaryAssessment` (current_salary, expected_salary,
  justified_salary, currency, rationale).

### 4. Adapters
- `storage.py`: presigned PUT URL (SSE-KMS), `get_bytes(s3_key)`.
- `text_extract.py`: `extract_native_text` (PyMuPDF); `needs_ocr` (chars-per-page).
- `ocr.py`: async Textract `start_analysis` / `wait_for_completion` (poll locally) /
  `parse_blocks` → text.
- `llm.py`: thin helpers over `langchain-aws` `ChatBedrockConverse` +
  `.with_structured_output(<PydanticModel>)` for reliable JSON (used by categorizer +
  both agents).

### 5. Agents
- `categorizer.py`: `categorize(text) -> DocType` via constrained structured output.
- `experience_agent.py`: `verify(resume_text, candidate) -> ExperienceVerification` —
  extract `ResumeExperience`, compare `total_years_experience` vs
  `candidate.expected_experience_years`, produce verdict + reasoning.
- `payslip_agent.py`: `assess(payslip_text, candidate, verification) -> SalaryAssessment`
  — extract `PayslipData.current_salary`, compare vs `candidate.expected_salary`, and have
  the model **predict a justified salary** given current vs expected salary and verified
  experience, with a rationale.

### 6. Pipeline core + LangGraph
- `pipeline/state.py`: `PipelineState` (submission_id, candidate, list of docs with
  text/type, partial results).
- `pipeline/stages.py`: `ingest` (load candidate + register submission/docs),
  `extract_text` (tiered, per doc), `categorize` (per doc), `verify_experience` (uses
  resume docs), `assess_salary` (uses payslip docs + verification), `persist` (write
  results, status DONE). FAILED on error with stored message.
- `pipeline/graph.py`: `StateGraph` — extract → categorize → conditional routing by
  `DocType` → experience + payslip agents → aggregate/persist. Single source of business
  logic, reused by local runner and Lambda.

### 7. Local runner + thin prod wrappers
- `main.py`: `python main.py --candidate <id> <resume.pdf> <payslip.pdf> ...` → upload to
  dev S3, simulate the ObjectCreated event by invoking the graph end-to-end against real
  AWS; print structured results + final status.
- `handlers/upload_handler.py` (API GW): create submission for a candidate, return
  presigned PUT URLs. `handlers/process_handler.py` (S3 event): invoke the graph.
  `handlers/results_handler.py` (API GW): return submission results. All thin wrappers
  over `pipeline`/`repository`.
- `infra/template.yaml`: SAM — S3 bucket + event, API Gateway, three Lambdas, SNS topic +
  Textract role, RDS reference, least-privilege IAM, KMS. **Not deployed in this MVP.**

### 8. Docs
- `README.md`: `aws configure`, create dev S3 bucket + KMS key, provision dev Postgres
  (local install or dev RDS — no Docker), `alembic upgrade head`, `python seed_candidates.py`,
  fill `.env`, run `python main.py ...`.

---

## Verification (end-to-end, against real AWS)

1. Configure AWS creds + dev S3 bucket/KMS + dev Postgres; `.env` from `.env.example`.
2. `alembic upgrade head`; `python seed_candidates.py` → a candidate with known
   expected_experience_years and expected_salary.
3. **Happy path:** `python main.py --candidate <id> samples/resume.pdf samples/payslip.pdf`
   → documents categorized correctly (RESUME / PAYSLIP), an `ExperienceVerification`
   comparing extracted vs expected years, and a `SalaryAssessment` with current vs expected
   salary and a **predicted justified_salary** + rationale. DB submission `status=DONE`.
4. **Textract fallback:** use a scanned payslip image → `ocr_method=textract`, salary still
   extracted.
5. **Discrepancy case:** candidate whose expected experience/salary diverge from the docs →
   verification verdict reflects the mismatch.
6. **Idempotency / failure:** re-run same submission (clean), and feed a corrupt file
   (`status=FAILED` with stored error, no crash).
7. `pytest tests/` passes (schemas + pipeline smoke).

Production deploy (`sam build && sam deploy`) and the React UI are deferred to later phases
once the local pipeline is validated.
