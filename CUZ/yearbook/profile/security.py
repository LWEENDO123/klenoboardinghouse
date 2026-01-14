# Yearbook/profile/security.py
# Yearbook/profile/security.py

import filetype

MAX_FILE_SIZE_MB = 25
ALLOWED_MIME_TYPES = {"image/jpeg"}  # normalize to JPEG on output; allow HEIC by extension if needed

def validate_image(file_bytes: bytes, filename: str) -> None:
    """
    Validate uploaded image bytes:
    - Enforce max file size
    - Detect MIME type using filetype
    - Allow JPEG by default, optionally HEIC by extension
    """
    # Size check
    if len(file_bytes) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError("File too large")

    # Type check using filetype
    kind = filetype.guess(file_bytes)
    if not kind:
        raise ValueError("Cannot determine file type")

    # Accept JPEG or HEIC (by extension)
    if kind.mime not in ALLOWED_MIME_TYPES and not filename.lower().endswith(".heic"):
        raise ValueError(f"Unsupported image type: {kind.mime}")

    # Optional: hook for malware scanning
    # scan_result = scan_bytes(file_bytes)  # integrate your scanner
    # if not scan_result.clean:
    #     raise ValueError("Malicious or corrupted image detected")




