import os
import logging
import uuid
import boto3
from botocore.client import Config

logger = logging.getLogger("core.storage")
logger.setLevel(logging.INFO)

# Env variables for Railway S3 bucket
RAILWAY_BUCKET = os.getenv("RAILWAY_BUCKET", "boardinghouse-bucket")
RAILWAY_ENDPOINT = os.getenv("RAILWAY_ENDPOINT")  # e.g. https://your-railway-s3-endpoint
RAILWAY_ACCESS_KEY = os.getenv("RAILWAY_ACCESS_KEY")
RAILWAY_SECRET_KEY = os.getenv("RAILWAY_SECRET_KEY")

# Initialize S3 client
s3_client = boto3.client(
    "s3",
    endpoint_url=RAILWAY_ENDPOINT,
    aws_access_key_id=RAILWAY_ACCESS_KEY,
    aws_secret_access_key=RAILWAY_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1"
)

def upload_file_bytes(key: str, file_bytes: bytes, content_type: str = "image/jpeg", public: bool = False) -> str:
    """
    Upload file bytes to Railway bucket and return a signed or public URL.
    """
    s3_client.put_object(
        Bucket=RAILWAY_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type
    )

    if public:
        return f"{RAILWAY_ENDPOINT}/{RAILWAY_BUCKET}/{key}"

    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": RAILWAY_BUCKET, "Key": key},
        ExpiresIn=3600
    )

__all__ = ["upload_file_bytes"]

def upload_compressed_image(university: str, student_id: str, file_bytes: bytes, filename: str, public: bool = False) -> str:
    unique_name = f"yearbook/{university}/{student_id}/{uuid.uuid4()}_{filename}".replace(" ", "_")
    return upload_file_bytes(unique_name, file_bytes, "image/jpeg", public=public)
