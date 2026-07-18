# Candidate Document Verification

An AI-powered recruitment pipeline that verifies candidate documents — experience letters and payslips — against recruiter expectations, with a human-in-the-loop review at each stage.

---

## The Problem

Recruiters spend hours manually reading through stacks of experience letters and payslips to verify:

- Does the candidate actually have the years of experience they claimed?
- Is their current salary what they stated?
- What is a fair offer to make?

This is slow, inconsistent, and error-prone at scale.

---

## How We Solve It

A three-phase AI pipeline where the recruiter stays in control at every step:

**Phase 1 — Categorise:** Upload documents, AI identifies what each one is.  
**Phase 2 — Extract & Verify:** AI agents run in parallel to extract experience and salary data.  
**Phase 3 — Analyse:** Final salary recommendation based on confirmed data.

The recruiter can correct AI mistakes at every phase before moving forward — no black box.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        RECRUITER UI                             │
└──────────┬──────────────────┬──────────────────┬───────────────┘
           │                  │                  │
           ▼                  ▼                  ▼
  POST /create_verification   POST /start_verification   POST /confirm_categories
  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────────┐
  │ Create record    │   │ Categorise docs  │   │ Save confirmed categories│
  │ Generate         │   │ (Nova Micro)     │   │ Fire async Lambda        │
  │ presigned S3 URLs│   │ Return categories│   └──────────┬───────────────┘
  └──────────────────┘   └──────────────────┘              │
                                                            ▼
                                              ┌─────────────────────────┐
                                              │  ProcessVerificationFn  │
                                              │  (LangGraph pipeline)   │
                                              │                         │
                                              │  load_docs_node         │
                                              │       │                 │
                                              │  ┌────┴────┐            │
                                              │  │PARALLEL │            │
                                              │  ├─────────┤            │
                                              │  │experience│           │
                                              │  │_node    │            │
                                              │  │(Sonnet) │            │
                                              │  ├─────────┤            │
                                              │  │payslip  │            │
                                              │  │_node    │            │
                                              │  │(Nova Pro)│           │
                                              │  └────┬────┘            │
                                              │       │                 │
                                              │  persist_node → DB      │
                                              └─────────────────────────┘
                                                            │
                                              POST /confirm_extraction
                                              ┌─────────────────────────┐
                                              │ Final salary prediction │
                                              │ on confirmed data       │
                                              └─────────────────────────┘


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
```

### Key Design Decisions

- **Agents run in parallel** — experience verification and payslip analysis run concurrently via LangGraph, cutting processing time roughly in half (~20s vs ~35s sequential).
- **Human-in-the-loop at every phase** — AI categories and extractions are shown to the recruiter before moving to the next phase. Corrections take priority over AI output.
- **Heavy work in a dedicated Lambda** — the 300s-timeout `ProcessVerificationFunction` handles the parallel agent calls; the API Lambda stays fast (<30s).
- **No credentials in code** — `DATABASE_URL` stored in AWS SSM Parameter Store, resolved at deploy time.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Mangum (Lambda adapter) |
| Orchestration | LangGraph (parallel agent fan-out) |
| AI Models | Amazon Nova Micro (categorise) · Nova Lite (extract) · Nova Pro (analyse) |
| Storage | AWS S3 (documents) · PostgreSQL (state + results) |
| Infrastructure | AWS Lambda + API Gateway via SAM/CloudFormation |
| Local Dev | uv (package manager) · uvicorn (dev server) |

---

## Local Setup

### Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL running locally
- AWS account with Bedrock model access enabled (Nova Micro, Nova Lite, Nova Pro)
- AWS CLI configured

### 1. Install dependencies

```bash
uv sync
```

### 2. Create the PostgreSQL database

```bash
createdb ai_assistance_db
```

Then create the table:

```sql
psql ai_assistance_db

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE candidate_verifications (
    verification_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        TEXT NOT NULL,
    candidate_name      TEXT NOT NULL,
    expected_experience_years FLOAT NOT NULL,
    expected_salary     FLOAT NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'INR',
    status              TEXT NOT NULL DEFAULT 'PENDING',
    document_keys       JSONB,
    confirmed_categories JSONB,
    experience_verification JSONB,
    salary_assessment   JSONB,
    summary             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values. AWS credentials are picked up automatically from `~/.aws/credentials` (standard `aws configure`). Only set `AWS_PROFILE` if you use a named profile.

> `LOCAL_MODE=true` makes `confirm_categories` run the pipeline inline instead of firing a Lambda — required for local development.

### 4. Create an S3 bucket

```bash
aws s3 mb s3://your-s3-bucket-name --region us-east-1
```

---

## Running Locally

### HTTP server (Postman / API testing)

```bash
uv run serve.py
```

Server starts at `http://localhost:4000`.  
Swagger UI available at `http://localhost:4000/docs`.

### Pipeline runner (direct, no HTTP)

```bash
uv run main.py
```

Uploads test files from `test/`, runs the full pipeline, prints results. Useful for testing the AI agents directly without HTTP overhead.

---

## API Flow

### Phase 1 — Upload & Categorise

**Create a verification and get presigned upload URLs:**

```bash
POST /dcp/create_verification
{
  "candidate_id": "candidate-001",
  "candidate_name": "Jane Smith",
  "expected_experience_years": 5.0,
  "expected_salary": 1500000,
  "currency": "INR",
  "files": [
    {"filename": "experience_letter.pdf"},
    {"filename": "payslip_oct.pdf"}
  ]
}
```

**Upload each file directly to S3** using the presigned URLs returned above (PUT request, binary body).

**Categorise the uploaded documents:**

```bash
POST /dcp/start_verification
{
  "verification_id": "<id from above>",
  "keys": ["<s3_key_1>", "<s3_key_2>"]
}
```

Returns: `[{ s3_key, filename, ai_category }]` — review and correct in the UI if needed.

---

### Phase 2 — Extract & Verify (Parallel Agents)

**Confirm categories and trigger parallel agent processing:**

```bash
POST /dcp/confirm_categories
{
  "verification_id": "<id>",
  "confirmed_categories": [
    {"s3_key": "<key1>", "doc_type": "EXPERIENCE_LETTER"},
    {"s3_key": "<key2>", "doc_type": "PAYSLIP"}
  ]
}
```

Experience agent and payslip agent run concurrently. Poll for results:

```bash
GET /dcp/get_verification/<verification_id>
```

When `status` is `DONE`, review the extracted `experience_verification` and `salary_assessment`.

---

### Phase 3 — Final Analysis

**Confirm extracted values (correct any AI errors) and get final recommendation:**

```bash
POST /dcp/confirm_extraction
{
  "verification_id": "<id>",
  "experience_years": 5.2,
  "current_salary": 1200000,
  "expected_salary": 1500000,
  "currency": "INR"
}
```

Returns the final `justified_salary` with rationale.

---

## Deploying to AWS

```bash
./deploy.sh
```

Requires:
- AWS profile `candidate-doc-verify-deployer` configured
- SSM Parameter `/recruiter-ai/prod/database-url` set as a `String` type:

```bash
aws ssm put-parameter \
  --name "/recruiter-ai/prod/database-url" \
  --value "postgresql://user:pass@your-rds-host:5432/dbname" \
  --type "String"
```

---

## Project Structure

```
src/recruitment/
├── app.py                          # FastAPI app + Mangum Lambda handler
├── shared/
│   ├── config.py                   # pydantic-settings (env vars)
│   ├── services/
│   │   ├── database.py             # PostgreSQL (raw psycopg, no ORM)
│   │   ├── storage.py              # S3 presigned URLs + file download
│   │   ├── text_extractor.py       # PyMuPDF text extraction
│   │   └── llm.py                  # Bedrock Converse wrapper
└── dcp/                            # Candidate Document Verification agent
    ├── routes.py                   # API endpoints
    ├── agents/
    │   ├── categorizer.py          # Nova Micro → DocType enum
    │   ├── experience.py           # Extract work history → verification verdict
    │   └── payslip.py              # Extract salary → justified offer
    ├── pipeline/
    │   ├── state.py                # LangGraph TypedDict state
    │   └── graph.py                # 4-node graph with parallel fan-out
    └── handlers/
        └── process_verification.py # Lambda handler → pipeline.invoke()
```
