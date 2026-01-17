import os
import uuid
import logging
import boto3
from botocore.client import Config

logger = logging.getLogger("core.storage")
logger.setLevel(logging.INFO)

# Railway Object Storage env vars
RAILWAY_BUCKET = os.getenv("RAILWAY_BUCKET")
RAILWAY_ENDPOINT = os.getenv("RAILWAY_ENDPOINT")
RAILWAY_ACCESS_KEY = os.getenv("RAILWAY_ACCESS_KEY")
RAILWAY_SECRET_KEY = os.getenv("RAILWAY_SECRET_KEY")

if not all([RAILWAY_BUCKET, RAILWAY_ENDPOINT, RAILWAY_ACCESS_KEY, RAILWAY_SECRET_KEY]):
    raise RuntimeError("❌ Missing Railway storage environment variables")

# S3 client
s3_client = boto3.client(
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
    content_type: str = "application/octet-stream",
    expires_in: int = 60 * 60 * 24 * 365 * 5,  # 5 years (effectively permanent)
) -> str:
    """
    Upload file and return a long-lived signed URL.
    """

    logger.info(f"📤 Uploading {key}")

    s3_client.put_object(
        Bucket=RAILWAY_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )

    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": RAILWAY_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )

__all__ = ["upload_file_bytes"]
