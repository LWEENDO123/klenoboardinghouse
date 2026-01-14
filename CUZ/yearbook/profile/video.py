# file: CUZ/yearbook/profile/video.py

import uuid
from CUZ.core.storage import upload_file_bytes

def upload_video_to_firebase(   # ✅ same name, but now Railway-backed
    university: str,
    student_id: str,
    file_bytes: bytes,
    filename: str,
    public: bool = False,
    expiry_hours: int = 24
) -> str:
    """
    Upload video file to Railway S3 bucket and return a signed or public URL.
    - Keeps the same function name for compatibility.
    - Signed URL expires after `expiry_hours` (default: 24h).
    """
    unique_name = f"videos/{university}/{student_id}/{uuid.uuid4()}_{filename}".replace(" ", "_")
    return upload_file_bytes(unique_name, file_bytes, "video/mp4", public=public)
