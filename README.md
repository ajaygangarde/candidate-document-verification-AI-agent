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
                                              │       ↓         ↓       │
                                              │  ┌──────────┐ ┌───────┐ │
                                              │  │experience│ │payslip│ │  ← PARALLEL
                                              │  │  _node   │ │extract│ │
                                              │  └────┬─────┘ └───┬───┘ │
                                              │       └─────┬─────┘     │
                                              │             ↓           │
                                              │    payslip_assess_node  │  ← fan-in
                                              │             ↓           │
                                              │       persist_node → DB │
                                              └─────────────────────────┘
                                                            │
                                              POST /confirm_extraction
                                              ┌─────────────────────────┐
                                              │ Final salary prediction │
                                              │ on confirmed data       │
                                              └─────────────────────────┘
```

### LangGraph Pipeline (5 nodes)

```
START
  ↓
load_docs_node
  ↓                    ↓
experience_node   payslip_extract_node   ← parallel fan-out
  ↓                    ↓
       payslip_assess_node               ← fan-in (waits for both)
             ↓
         persist_node
             ↓
            END
```

### Key Design Decisions

- **Agents run in parallel** — experience verification and payslip extraction run concurrently via LangGraph, cutting processing time roughly in half (~20s vs ~35s sequential).
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
- AWS CLI configured (`aws configure`)

### 1. Install dependencies

```bash
uv sync
```

### 2. Create the PostgreSQL database

```bash
createdb ai_assistance_db
```

Run the migration to create the table:

```bash
psql ai_assistance_db < infra/migrations/001_initial.sql
```

Or manually via psql:

```bash
psql ai_assistance_db
```

```sql
\i infra/migrations/001_initial.sql
```

The migration creates:

```sql
CREATE TABLE candidate_verifications (
    verification_id           UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id              TEXT      NOT NULL,
    candidate_name            TEXT,
    expected_experience_years FLOAT     NOT NULL,
    expected_salary           FLOAT     NOT NULL,
    currency                  TEXT      NOT NULL DEFAULT 'INR',
    status                    TEXT      NOT NULL DEFAULT 'PENDING'
                                        CHECK (status IN ('PENDING', 'PROCESSING', 'DONE', 'FAILED')),
    document_keys             JSONB     NOT NULL DEFAULT '[]',
    confirmed_categories      JSONB,
    experience_verification   JSONB,
    salary_assessment         JSONB,
    summary                   TEXT,
    created_at                TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```env
AWS_REGION=us-east-1
S3_BUCKET=your-s3-bucket-name
DATABASE_URL=postgresql://your_user:your_password@localhost:5432/ai_assistance_db
LOCAL_MODE=true
```

AWS credentials are picked up automatically from `~/.aws/credentials` (standard `aws configure`). Only set `AWS_PROFILE` if you use a named profile.

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

Server starts at `http://localhost:8080`.  
Swagger UI available at `http://localhost:8080/docs`.

### Pipeline runner (direct, no HTTP)

```bash
uv run main.py
```

Uploads test files from `test/`, runs the full pipeline end-to-end, and prints results. Useful for testing AI agents directly without HTTP overhead.

---

## Benchmark Results

End-to-end test run against real documents using `uv run main.py`.

### Test Configuration

| Parameter | Value |
|---|---|
| Documents | 4 experience letters + 3 payslips |
| Payslip employer | Me India Pvt. Ltd. |
| Payslip months | Oct · Nov · Dec 2025 |
| Text extraction | 2 native PDF · 2 scanned (Nova Lite vision fallback) |
| Expected experience | 7 years |
| Expected salary | ₹35,00,000 |
| Company segment | TECH_MNC |
| Models | Nova Micro (categorise) · Nova Lite (extract) · Nova Pro (analyse) |

### Output

```json
{
  "experience_verification": {
    "extracted_years": 9.7,
    "expected_years": 7.0,
    "verdict": "EXCEEDS_EXPECTATION",
    "discrepancy": null,
    "confidence": 0.9,
    "notes": "Candidate exceeds expectation by 2.7 yrs (4 role(s) found).",
    "gap_months": 32.4,
    "gap_flag": "MATCH",
    "llm_execution_time_seconds": 3.69
  },
  "salary_assessment": {
    "current_salary": 2802216.0,
    "expected_salary": 3500000.0,
    "salary_gap": null,
    "above_benchmark": null,
    "justified_salary": 3500000.0,
    "currency": "INR",
    "rationale": "The justified salary of INR 3500000 is proposed to align with the expected recruiter benchmark and to bridge 65% of the salary gap, ensuring a competitive offer within the target raise range of 20%-30%.",
    "recent_increment": {
      "trend": "STABLE",
      "previous_salary": 2802216.0,
      "change_amount": 0.0,
      "change_percentage": 0.0,
      "change_confidence": "low"
    },
    "analysis_time_seconds": 1.29
  }
}
```

> `salary_gap` and `above_benchmark` are populated by the LangGraph pipeline (HTTP flow via `confirm_categories`). The direct batch runner (`uv run main.py`) does not pass through that node — these fields will be non-null in the full API flow.

### Evaluation

#### Experience Verification

| | Value |
|---|---|
| Roles extracted | 4 |
| Total years extracted | 9.7 yrs |
| Expected by recruiter | 7.0 yrs |
| Surplus | +2.7 yrs above expectation |
| Verdict | `EXCEEDS_EXPECTATION` — not a concern |
| `gap_months: +32.4` | Positive = candidate exceeds expectation by 2.7 years |
| `gap_flag: MATCH` | `HIGH_DISCREPANCY` only fires when candidate is **below** expectation |

`DISCREPANCY` only fires when the candidate falls short of the recruiter's minimum. More experience than required is `EXCEEDS_EXPECTATION` — a positive signal. `gap_months` is positive when the candidate exceeds, negative when they fall short.

#### Salary Assessment

The justified salary is calculated using the TECH_MNC segment rules:

```
Current CTC   : ₹28,02,216  (₹28.0L)   ← grounded from monthly_earnings × 12
Expected CTC  : ₹35,00,000  (₹35.0L)
Gap           : ₹ 6,97,784  (₹ 7.0L)

Raise-based offer  : ₹28.0L × 1.25 (mid of 20–30%)  = ₹35,02,770
Gap-based offer    : ₹28.0L + (₹7.0L × 0.65)         = ₹32,55,776
Justified salary   : max(35.02L, 32.55L)              = ₹35,02,770
Capped at expected : min(35.02L, 35.00L)              = ₹35,00,000  ✓
```

Raise-based offer slightly exceeded the benchmark by ₹2,770 and was capped at `expected_salary`. The candidate receives the full recruiter benchmark.

#### Salary Trend

```json
"recent_increment": {
  "trend": "STABLE",
  "change_percentage": 0.0,
  "change_confidence": "low"
}
```

All three payslips (Oct–Dec 2025) show the same `monthly_earnings` after grounding — salary is stable. `change_confidence: low` because the 0% change falls within the <5% payroll noise band (Leave Without Pay, arrears, and bonuses can shift a single month by 2-4% without a real salary revision).

#### Salary Extraction — Grounding Applied

The pipeline uses a value provenance model to anchor every `annual_ctc` to its source:

| Source | Confidence | When |
|---|---|---|
| `annual_ctc` | `high` | Explicit Annual Summary or Form 16 section found in payslip |
| `estimated_from_monthly` | `medium` | No annual section — computed as `monthly_earnings × 12` |
| `form_16` | `high` | Form 16 document submitted by candidate |

In this run, the December payslip's extracted `annual_ctc` diverged from `monthly_earnings × 12` by more than 30% (extraction noise from IBM's Income Tax Projection section). The pipeline automatically fell back to `estimated_from_monthly`, producing a consistent ₹28L across all three months instead of the misleading ₹22.4L seen in earlier runs.

---

## API Flow

### Phase 1 — Upload & Categorise

**Step 1 — Create a verification record and get presigned S3 upload URLs:**

```
POST /dcp/create_verification
```

```json
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

Response includes `verification_id` and a `presigned_urls` list.

**Step 2 — Upload each file directly to S3** using the presigned URLs (PUT request, binary body, no auth header needed).

**Step 3 — Categorise the uploaded documents:**

```
POST /dcp/start_verification
```

```json
{
  "verification_id": "<id from step 1>",
  "keys": ["<s3_key_1>", "<s3_key_2>"]
}
```

Returns: `[{ s3_key, filename, ai_category }]` — review and correct in the UI if needed.

---

### Phase 2 — Extract & Verify (Parallel Agents)

**Confirm categories and trigger parallel agent processing:**

```
POST /dcp/confirm_categories
```

```json
{
  "verification_id": "<id>",
  "confirmed_categories": [
    {"s3_key": "<key1>", "doc_type": "EXPERIENCE_LETTER"},
    {"s3_key": "<key2>", "doc_type": "PAYSLIP"}
  ]
}
```

With `LOCAL_MODE=true`, this runs the full LangGraph pipeline inline and returns when done. In production it fires an async Lambda and returns `{ "status": "processing" }` immediately.

**Poll for results (production only):**

```
GET /dcp/get_verification/<verification_id>
```

When `status` is `DONE`, the response includes `experience_verification` and `salary_assessment`.

---

### Phase 3 — Final Analysis

**Confirm extracted values (correct any AI errors) and get the final salary recommendation:**

```
POST /dcp/confirm_extraction
```

```json
{
  "verification_id": "<id>",
  "experience_years": 5.2,
  "current_salary": 1200000,
  "expected_salary": 1500000,
  "currency": "INR"
}
```

Returns the final `justified_salary` with a written rationale from the model.

---

## Deploying to AWS

### Prerequisites

1. **AWS CLI** configured with a deployment profile:

   ```bash
   aws configure --profile candidate-doc-verify-deployer
   ```

2. **SSM Parameter** — store your production `DATABASE_URL` in AWS SSM Parameter Store (String type, not SecureString — CloudFormation's `{{resolve:ssm:...}}` only supports String):

   ```bash
   aws ssm put-parameter \
     --name "/recruiter-ai/prod/database-url" \
     --value "postgresql://user:pass@your-rds-host:5432/dbname" \
     --type "String" \
     --profile candidate-doc-verify-deployer
   ```

3. **Bedrock model access** enabled in your AWS account for:
   - `amazon.nova-micro-v1:0`
   - `amazon.nova-lite-v1:0`
   - `amazon.nova-pro-v1:0`

### Deploy

```bash
./deploy.sh
```

This script:
1. Verifies AWS credentials
2. Exports Python dependencies to `src/requirements.txt`
3. Runs `sam build` using `infra/prod-template.yaml`
4. Patches the Linux `psycopg[binary]` wheel into each Lambda build artifact (SAM builds on macOS install the macOS wheel; Lambda requires Linux x86_64)
5. Runs `sam deploy` — creates or updates the CloudFormation stack `candidate-document-processing`

### What gets created

| Resource | Name |
|---|---|
| API Lambda | `CDV-Api` |
| Processing Lambda | `CDV-ProcessVerification` (300s timeout) |
| API Gateway | `candidate-document-processing` (prod stage) |
| S3 Bucket | Auto-named by CloudFormation |

### Build only (no deploy)

```bash
./build.sh
```

Runs `sam build` without deploying — useful to verify the build succeeds before a full deploy.

### Tear down

```bash
./cleanup-stack.sh
```

Deletes the CloudFormation stack and all associated resources.

---

## Project Structure

```
src/recruitment/
├── app.py                          # FastAPI app + Mangum Lambda handler
├── shared/
│   ├── config.py                   # pydantic-settings (reads .env + Lambda env vars)
│   ├── services/
│   │   ├── database.py             # PostgreSQL (raw psycopg, no ORM)
│   │   ├── storage.py              # S3 presigned URLs + file download
│   │   ├── text_extractor.py       # PyMuPDF text extraction
│   │   └── llm.py                  # Bedrock Converse wrapper
└── dcp/                            # Candidate Document Verification
    ├── routes.py                   # API endpoints (3 phases)
    ├── agents/
    │   ├── categorizer.py          # Nova Micro → DocType enum
    │   ├── experience.py           # Extract work history → verification verdict
    │   └── payslip.py              # Extract salary → justified offer
    ├── pipeline/
    │   ├── state.py                # LangGraph TypedDict state
    │   └── graph.py                # 5-node graph: load → [experience ‖ payslip_extract] → payslip_assess → persist
    └── handlers/
        └── process_verification.py # Lambda handler → pipeline.invoke()

infra/
├── prod-template.yaml              # SAM/CloudFormation — Lambda + API Gateway
└── migrations/
    └── 001_initial.sql             # PostgreSQL schema
```
