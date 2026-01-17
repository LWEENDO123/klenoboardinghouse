import os
import logging
import uuid
import boto3
from botocore.client import Config
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger("core.storage")
logger.setLevel(logging.INFO)

# =============================
# ENV VARS
# =============================
RAILWAY_BUCKET = os.getenv("RAILWAY_BUCKET")
RAILWAY_ENDPOINT = os.getenv("RAILWAY_ENDPOINT")
RAILWAY_ACCESS_KEY = os.getenv("RAILWAY_ACCESS_KEY")
RAILWAY_SECRET_KEY = os.getenv("RAILWAY_SECRET_KEY")
BASE_API_URL = os.getenv("BASE_API_URL")  # e.g. https://api.yourapp.com

if not all([
    RAILWAY_BUCKET,
    RAILWAY_ENDPOINT,
    RAILWAY_ACCESS_KEY,
    RAILWAY_SECRET_KEY,
    BASE_API_URL,
]):
    raise RuntimeError("❌ Missing Railway storage environment variables")

# =============================
# S3 CLIENT (Railway / MinIO)
# =============================
s3_client = boto3.client(
    "s3",
    endpoint_url=RAILWAY_ENDPOINT,
    aws_access_key_id=RAILWAY_ACCESS_KEY,
    aws_secret_access_key=RAILWAY_SECRET_KEY,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

# =============================
# FASTAPI ROUTER (MEDIA)
# =============================
router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{key:path}")
async def serve_media(key: str):
    """
    Permanent media access endpoint.
    Example:
    /media/ALL/admin/uuid_image.jpg
    """
    try:
        obj = s3_client.get_object(
            Bucket=RAILWAY_BUCKET,
            Key=key,
        )

        return StreamingResponse(
            obj["Body"],
            media_type=obj.get("ContentType", "application/octet-stream"),
            headers={
                "Cache-Control": "public, max-age=31536000, immutable"
            },
        )

    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="File not found")

    except Exception as e:
        logger.exception("❌ Failed to fetch media")
        raise HTTPException(status_code=500, detail="Media fetch failed")


# =============================
# STORAGE HELPERS
# =============================
def upload_file_bytes(
    key: str,
    file_bytes: bytes,
    content_type: str = "image/jpeg",
) -> str:
    """
    Upload file to Railway Object Storage (PERMANENT).
    Returns a PERMANENT API URL.
    """
    logger.info(f"📤 Uploading file: {key}")

    s3_client.put_object(
        Bucket=RAILWAY_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )

    # ✅ Permanent URL via your API
    return f"{BASE_API_URL}/media/{key}"


def upload_compressed_image(
    university: str,
    student_id: str,
    file_bytes: bytes,
    filename: str,
) -> str:
    key = f"yearbook/{university}/{student_id}/{uuid.uuid4()}_{filename}".replace(" ", "_")
    return upload_file_bytes(
        key=key,
        file_bytes=file_bytes,
        content_type="image/jpeg",
    )


__all__ = [
    "router",
    "upload_file_bytes",
    "upload_compressed_image",
]
