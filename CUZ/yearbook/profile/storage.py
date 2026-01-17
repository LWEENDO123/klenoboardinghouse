import os
import logging
import uuid
import boto3
from botocore.client import Config

logger = logging.getLogger("core.storage")
logger.setLevel(logging.INFO)

# ✅ Railway Object Storage env vars (ONLY THESE)
RAILWAY_BUCKET = os.getenv("RAILWAY_BUCKET")
RAILWAY_ENDPOINT = os.getenv("RAILWAY_ENDPOINT")
RAILWAY_ACCESS_KEY = os.getenv("RAILWAY_ACCESS_KEY")
RAILWAY_SECRET_KEY = os.getenv("RAILWAY_SECRET_KEY")


def _validate_env():
    missing = []
    for name, value in {
        "RAILWAY_BUCKET": RAILWAY_BUCKET,
        "RAILWAY_ENDPOINT": RAILWAY_ENDPOINT,
        "RAILWAY_ACCESS_KEY": RAILWAY_ACCESS_KEY,
        "RAILWAY_SECRET_KEY": RAILWAY_SECRET_KEY,
    }.items():
        if not value:
            missing.append(name)

    if missing:
        raise RuntimeError(
            f"❌ Missing Railway storage environment variables: {', '.join(missing)}"
        )


# ✅ Initialize S3 client lazily (safe)
def _get_s3_client():
    _validate_env()

    return boto3.client(
        "s3",
        endpoint_url=RAILWAY_ENDPOINT,
        aws_access_key_id=RAILWAY_ACCESS_KEY,
        aws_secret_access_key=RAILWAY_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def upload_file_bytes(
    key: str,
    file_bytes: bytes,
    content_type: str = "image/jpeg",
    permanent: bool = True,
) -> str:
    """
    Upload bytes to Railway Object Storage.

    - permanent=True → returns a SIGNED URL (recommended)
    - Railway does NOT support public-read objects
    """

    s3 = _get_s3_client()

    logger.info(f"📤 Uploading file: {key}")

    s3.put_object(
        Bucket=RAILWAY_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )

    # ✅ Railway requires signed URLs (even for "public" content)
    return s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": RAILWAY_BUCKET,
            "Key": key,
        },
        ExpiresIn=60 * 60 * 24 * 365 * 10,  # 10 years (effectively permanent)
    )


def upload_compressed_image(
    university: str,
    student_id: str,
    file_bytes: bytes,
    filename: str,
) -> str:
    """
    Upload compressed image and return a long-lived signed URL.
    """

    key = (
        f"yearbook/{university}/{student_id}/"
        f"{uuid.uuid4()}_{filename}"
    ).replace(" ", "_")

    return upload_file_bytes(
        key=key,
        file_bytes=file_bytes,
        content_type="image/jpeg",
    )


__all__ = ["upload_file_bytes", "upload_compressed_image"]
