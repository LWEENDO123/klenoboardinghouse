import os
import logging
import uuid
import boto3
from botocore.client import Config

logger = logging.getLogger("core.storage")
logger.setLevel(logging.INFO)

# Railway Object Storage env vars
RAILWAY_BUCKET = os.getenv("RAILWAY_BUCKET")
RAILWAY_ENDPOINT = os.getenv("RAILWAY_ENDPOINT")  # e.g. https://storage.railway.app
RAILWAY_ACCESS_KEY = os.getenv("RAILWAY_ACCESS_KEY")
RAILWAY_SECRET_KEY = os.getenv("RAILWAY_SECRET_KEY")

if not all([RAILWAY_BUCKET, RAILWAY_ENDPOINT, RAILWAY_ACCESS_KEY, RAILWAY_SECRET_KEY]):
    raise RuntimeError("❌ Railway S3 environment variables are missing")

# Initialize S3 client (Railway / MinIO)
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
    content_type: str = "image/jpeg",
    expires_in: int = 60 * 60 * 24 * 7,  # 7 days
) -> str:
    """
    Upload bytes to Railway Object Storage and return a signed GET URL.
    """

    logger.info(f"📤 Uploading file to bucket={RAILWAY_BUCKET}, key={key}")

    s3_client.put_object(
        Bucket=RAILWAY_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )

    signed_url = s3_client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": RAILWAY_BUCKET,
            "Key": key,
        },
        ExpiresIn=expires_in,
    )

    logger.info(f"🔐 Signed URL generated (expires in {expires_in}s)")
    return signed_url


def upload_compressed_image(
    university: str,
    student_id: str,
    file_bytes: bytes,
    filename: str,
    expires_in: int = 60 * 60 * 24 * 7,
) -> str:
    """
    Upload compressed image and return signed URL.
    """
    key = f"yearbook/{university}/{student_id}/{uuid.uuid4()}_{filename}".replace(" ", "_")
    return upload_file_bytes(
        key=key,
        file_bytes=file_bytes,
        content_type="image/jpeg",
        expires_in=expires_in,
    )


__all__ = ["upload_file_bytes", "upload_compressed_image"]
