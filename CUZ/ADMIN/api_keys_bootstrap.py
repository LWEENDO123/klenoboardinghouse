# CUZ/ADMIN/api_keys_bootstrap.py
from datetime import datetime, timedelta, timezone
import uuid
from core.firebase import db

def ensure_initial_admin_api_key():
    # Check if any non-revoked admin key exists
    docs = db.collection("API_KEYS").where("role", "==", "admin").where("revoked", "==", False).stream()
    has_active_admin_key = any(True for _ in docs)

    if has_active_admin_key:
        return None  # already present

    key_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=90)

    db.collection("API_KEYS").document(key_id).set({
        "role": "admin",
        "revoked": False,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "last_used": None,
        "created_by": "bootstrap@system"
    })
    return key_id  # Return so you can log/copy it on startup
