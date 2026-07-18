CREATE EXTENSION IF NOT EXISTS "pgcrypto";

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
