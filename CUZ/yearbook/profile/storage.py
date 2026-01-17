import os
import json
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

def ensure_bucket_public():
    """
    Sets a bucket policy to allow public 'read' access to all objects.
    This fixes the 'Access Denied' issue for generated links.
    """
    public_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicReadGetObject",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{RAILWAY_BUCKET}/*"
            }
        ]
    }
    try:
        s3_client.put_bucket_policy(
            Bucket=RAILWAY_BUCKET, 
            Policy=json.dumps(public_policy)
        )
        logger.info(f"✅ Public policy applied to bucket: {RAILWAY_BUCKET}")
    except Exception as e:
        logger.warning(f"⚠️ Could not set bucket policy: {e}")

def upload_file_bytes(
    key: str,
    file_bytes: bytes,
    content_type: str = "application/octet-stream",
) -> str:
    """
    Uploads file and returns a permanent public URL.
    """
    logger.info(f"📤 Uploading {key}")

    # ACL='public-read' tells the storage that this specific file is public
    s3_client.put_object(
        Bucket=RAILWAY_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
        ACL='public-read' 
    )

    # Clean the endpoint to remove trailing slashes
    base_url = RAILWAY_ENDPOINT.rstrip("/")
    
    # Return a permanent direct link (No expiration tokens!)
    return f"{base_url}/{RAILWAY_BUCKET}/{key}"

__all__ = ["upload_file_bytes", "ensure_bucket_public"]
