import boto3
import json
from recruitment.shared.config import settings
from recruitment.dcp.pipeline.batch import run_batch
from recruitment.shared.services.database import create_candidate_verification

s3 = boto3.client("s3", region_name=settings.aws_region)

CANDIDATE_ID = "candidate-001"

# Experience letters — full tenure documents (joining → relieving date)
EXPERIENCE_LETTERS = [
    "./test/infodreamz-experience-letter.pdf",
    "./test/experience_and_service_letter.pdf",
    "./test/relieving-and-experience-letter.pdf",
    "./test/Relieving and Experience Letter - 1037538.pdf",
]

# Payslips — last 3 months
PAYSLIPS = [
    "./test/20251231Payslip.pdf",
    "./test/20251130Payslip.pdf",
    "./test/20251031Payslip.pdf",
]

# Skipped — OTHER category (not processed by pipeline)
# "./test/OfferLetter_GangardeAjay_19-Jun-2024_ 13_53_49.pdf"

LOCAL_FILES = EXPERIENCE_LETTERS + PAYSLIPS

# Step 1 — create verification row in DB
verification_id = create_candidate_verification(
    candidate_id=CANDIDATE_ID,
    candidate_name="Ajay Gangarde",
    expected_experience_years=5.0,
    expected_salary=90000.0,
    currency="INR",
)
print(f"\nCandidate Verification: {verification_id}")

# Step 2 — upload each local file to S3
s3_keys = []
print("Uploading files to S3...")
for local_path in LOCAL_FILES:
    filename = local_path.split("/")[-1]
    key = f"candidate_verifications/{CANDIDATE_ID}/{verification_id}/{filename}"
    s3.upload_file(local_path, settings.s3_bucket, key)
    s3_keys.append(key)
    print(f"  Uploaded: {key}")

from recruitment.shared.services.text_extractor import extract_text, extract_payslip_bytes
from recruitment.dcp.agents.payslip import extract_payslip

for payslip_path in PAYSLIPS:
    with open(payslip_path, "rb") as f:
        pdf_bytes = f.read()
    text, method = extract_text(pdf_bytes)
    print(f"\n{payslip_path}:")
    print(f"  Native text (first 500 chars): {text[:500]}")
    
    # Test extraction directly
    payslip_data, time_taken = extract_payslip([pdf_bytes])
    print(f"  Extracted annual_ctc: {payslip_data.annual_ctc}")
    print(f"  Extracted monthly_earnings: {payslip_data.monthly_earnings}")


# Step 3 — run the full pipeline
print(f"\nProcessing {len(s3_keys)} documents...")
results = run_batch(
    verification_id=verification_id,
    s3_keys=s3_keys,
)

# Step 4 — print results
print("\n--- Verification Results ---")
print(json.dumps(results, indent=2))
