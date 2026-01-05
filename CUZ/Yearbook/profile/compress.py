# file: CUZ/Yearbook/profile/compress.py

from PIL import Image
import io
import uuid
from datetime import timedelta
from core.firebase import bucket   # ✅ use the bucket from core/firebase.py

def compress_to_720(image_bytes: bytes, quality: int = 80) -> bytes:
    """
    Resize and compress image to 1280x720 max, return as JPEG bytes.
    - Converts to RGB
    - Resizes while maintaining aspect ratio
    - Saves as JPEG with given quality (default 80)
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        img.thumbnail((1280, 720))  # resize in-place, keeps aspect ratio
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue()

def upload_to_firebase(
    university: str,
    student_id: str,
    file_bytes: bytes,
    filename: str,
    expiry_hours: int = 24
) -> str:
    """
    Upload compressed image to Firebase Storage and return a signed URL.
    - Files are private by default (no make_public).
    - Signed URL expires after `expiry_hours` (default: 24h).
    """
    unique_name = f"{university}/{student_id}/{uuid.uuid4()}_{filename}"
    blob = bucket.blob(unique_name)
    blob.upload_from_string(file_bytes, content_type="image/jpeg")

    # Generate signed URL (time-limited access)
    url = blob.generate_signed_url(expiration=timedelta(hours=expiry_hours))
    return url
