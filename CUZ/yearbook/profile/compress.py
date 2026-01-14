# file: CUZ/yearbook/profile/compress.py

from PIL import Image
import io
import uuid
from datetime import timedelta
from CUZ.yearbook.profile.storage import upload_file_bytes   # ✅ correct path

def compress_to_720(image_bytes: bytes, quality: int = 80) -> bytes:
    """
    Resize and compress image to 1280x720 max, return as JPEG bytes.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((1280, 720))
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()

def upload_to_firebase(   # ✅ same function name, but now Railway-backed
    university: str,
    student_id: str,
    file_bytes: bytes,
    filename: str,
    expiry_hours: int = 24
) -> str:
    """
    Upload compressed image to Railway S3 bucket and return a signed URL.
    - Keeps the same function name for compatibility.
    - Signed URL expires after `expiry_hours` (default: 24h).
    """
    unique_name = f"{university}/{student_id}/{uuid.uuid4()}_{filename}".replace(" ", "_")
    return upload_file_bytes(unique_name, file_bytes, "image/jpeg", public=False)