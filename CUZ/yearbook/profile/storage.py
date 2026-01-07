# file: CUZ/yearbook/profile/storage.py
import uuid
from CUZ.core.firebase import bucket   # ✅ fixed import path

def upload_compressed_image(
    university: str,
    student_id: str,
    file_bytes: bytes,
    filename: str,
    public: bool = False
) -> str:
    unique_name = f"yearbook/{university}/{student_id}/{uuid.uuid4()}_{filename}".replace(" ", "_")
    blob = bucket.blob(unique_name)
    blob.upload_from_string(file_bytes, content_type="image/jpeg")
    if public:
        blob.make_public()
        return blob.public_url
    return blob.generate_signed_url(expiration=3600)
