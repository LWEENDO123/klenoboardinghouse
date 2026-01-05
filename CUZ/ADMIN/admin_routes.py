#CUZ/ADMIN/admin_routes.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone
import uuid

from core.firebase import db
from .security import get_current_admin  # ensures only admins can call these

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------------
# CREATE NEW API KEY
# ---------------------------
@router.post("/api-keys")
async def create_api_key(
    role: str,
    expires_in_days: int = 30,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Create a new API key scoped to a role (student, landlord, admin, service).
    Default expiry = 30 days.
    """
    key_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=expires_in_days)

    db.collection("API_KEYS").document(key_id).set({
        "role": role,
        "revoked": False,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "last_used": None,
        "created_by": current_admin["email"],
    })

    # ✅ Return the actual key so you can copy it immediately
    return {
        "api_key": key_id,
        "role": role,
        "expires_at": expires_at.isoformat()
    }

# ---------------------------
# REVOKE API KEY
# ---------------------------
@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Revoke an API key immediately and print it back.
    """
    doc = db.collection("API_KEYS").document(key_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="API key not found")

    db.collection("API_KEYS").document(key_id).update({"revoked": True})
    return {
        "message": f"API key {key_id} revoked",
        "api_key": key_id
    }

# ---------------------------
# LIST API KEYS
# ---------------------------
@router.get("/api-keys")
async def list_api_keys(current_admin: dict = Depends(get_current_admin)):
    """
    List all API keys with metadata (role, revoked, expiry).
    Includes the actual key IDs so you can copy them.
    """
    docs = db.collection("API_KEYS").stream()
    keys = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id  # this is the actual API key
        keys.append(data)
    return {
        "count": len(keys),
        "keys": keys
    }
