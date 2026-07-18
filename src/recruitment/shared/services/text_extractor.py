import boto3
import fitz
from recruitment.shared.config import settings
from recruitment.shared.logging import logger

CHARS_PER_PAGE_THRESHOLD = 100
MAX_VISION_PAGES = 20

bedrock = boto3.client("bedrock-runtime", region_name=settings.aws_region)


def _extract_native_text(pdf_bytes: bytes) -> tuple[str, int]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    logger.info("Native text extraction done", pages=page_count, chars=len(text))
    return text, page_count


def _needs_ocr(text: str, page_count: int) -> bool:
    if page_count == 0:
        return True
    return (len(text) / page_count) < CHARS_PER_PAGE_THRESHOLD


def _pdf_to_images(pdf_bytes: bytes) -> list[bytes]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        images.append(pix.tobytes("png"))
    doc.close()
    return images[:MAX_VISION_PAGES]


def _nova_lite_vision(pdf_bytes: bytes, prompt: str) -> str:
    images = _pdf_to_images(pdf_bytes)
    content = [
        {"image": {"format": "png", "source": {"bytes": img}}}
        for img in images
    ]
    content.append({"text": prompt})
    response = bedrock.converse(
        modelId="amazon.nova-lite-v1:0",
        messages=[{"role": "user", "content": content}],
    )
    text = response["output"]["message"]["content"][0]["text"]
    logger.info("Nova Lite vision extraction done", pages=len(images), chars=len(text))
    return text


def extract_text(pdf_bytes: bytes) -> tuple[str, str]:
    """Extract text from a native PDF. For payslips use extract_payslip_bytes instead."""
    text, page_count = _extract_native_text(pdf_bytes)

    if not _needs_ocr(text, page_count):
        return text, "native"

    logger.info("Scanned document detected — falling back to Nova Lite vision", pages=page_count)
    text = _nova_lite_vision(
        pdf_bytes,
        prompt="Extract all text from this document exactly as it appears. Preserve dates, names, company names, and any numbers.",
    )
    return text, "nova_lite_vision"


def extract_payslip_bytes(pdf_bytes: bytes) -> bytes:
    """Return raw PDF bytes for payslips — caller sends directly to LLM via Converse API."""
    return pdf_bytes
