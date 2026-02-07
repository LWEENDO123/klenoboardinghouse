from fastapi import APIRouter, HTTPException, Form
import uuid
import logging
import subprocess
import tempfile
import os
from CUZ.yearbook.profile.storage import s3_client, RAILWAY_BUCKET, BASE_URL

logger = logging.getLogger("video_upload")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/videos", tags=["videos"])

async def optimize_video_s3(key: str):
    """
    Download a video from S3, re-encode with faststart, and upload back.
    """
    local_in = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    local_out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name

    try:
        # 1. Download from S3
        s3_client.download_file(RAILWAY_BUCKET, key, local_in)

        # 2. Run ffmpeg with faststart
        cmd = [
            "ffmpeg", "-i", local_in,
            "-c:v", "libx264", "-preset", "fast",
            "-movflags", "+faststart",
            local_out
        ]
        subprocess.run(cmd, check=True)

        # 3. Upload back to S3 (overwrite same key)
        s3_client.upload_file(
            local_out, RAILWAY_BUCKET, key,
            ExtraArgs={"ContentType": "video/mp4", "ACL": "public-read"}
        )

        logger.info(f"✅ Optimized and re-uploaded video: {key}")
    except Exception as e:
        logger.error(f"❌ Video optimization failed for {key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Video optimization failed: {str(e)}")
    finally:
        # Cleanup temp files
        for f in [local_in, local_out]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass


@router.post("/presign")
async def get_presigned_video_url(
    university: str = Form(...),
    student_id: str = Form(...),
    filename: str = Form(...)
):
    """
    Generate a presigned URL for direct video upload to Railway S3.
    Client must call /videos/optimize after upload completes.
    """
    try:
        logger.info(f"🎬 Presign request received: university={university}, student_id={student_id}, filename={filename}")

        unique_name = f"videos/{university}/{student_id}/{uuid.uuid4()}_{filename}".replace(" ", "_")
        logger.info(f"Generated unique key: {unique_name}")

        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": RAILWAY_BUCKET,
                "Key": unique_name,
                "ContentType": "video/mp4"
            },
            ExpiresIn=3600
        )
        logger.info(f"Presigned URL generated successfully for key={unique_name}")

        response = {
            "upload_url": presigned_url,
            "file_key": unique_name,
            "proxy_url": f"{BASE_URL}/media/{unique_name}"
        }

        logger.info(f"Returning presign response: {response}")
        return response

    except Exception as e:
        logger.error(f"❌ Error generating presigned URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating presigned URL: {str(e)}")


@router.post("/optimize")
async def optimize_uploaded_video(file_key: str = Form(...)):
    """
    Optimize a video after it has been uploaded.
    Client should call this endpoint once upload is complete.
    """
    logger.info(f"📦 Optimize request received for key={file_key}")
    await optimize_video_s3(file_key)
    return {"message": f"Optimization started for {file_key}"}
