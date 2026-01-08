# USERS/Appkey.py
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from CUZ.core.firebase import db
from datetime import datetime, timezone

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """
    Verify that the provided API key exists, is not revoked, and is not expired.
    Keys are stored in Firestore under API_KEYS/{key_id}.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing API key"
        )

    doc = db.collection("API_KEYS").document(api_key).get()
    if not doc.exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )

    data = doc.to_dict()
    if data.get("revoked", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key revoked"
        )

    expires_at = data.get("expires_at")
    if expires_at:
        expires_at = datetime.fromisoformat(expires_at)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key expired"
            )

    # Update last_used timestamp
    db.collection("API_KEYS").document(api_key).update({
        "last_used": datetime.now(timezone.utc).isoformat()
    })

    return api_key



