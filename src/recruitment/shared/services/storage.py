import boto3
from recruitment.shared.config import settings
from recruitment.shared.logging import logger


def _s3():
    session = boto3.Session(
        profile_name=settings.aws_profile,
        region_name=settings.aws_region,
    )
    return session.client("s3")

def generate_presigned_upload_url(s3_key: str, content_type: str = "application/pdf") -> str:
    url = _s3().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=900,
    )
    logger.info("Generated presigned URL", s3_key=s3_key)
    return url


def get_file_bytes(s3_key: str) -> bytes:
    response = _s3().get_object(Bucket=settings.s3_bucket, Key=s3_key)
    return response["Body"].read()
