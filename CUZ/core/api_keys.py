# CUZ/core/api_keys.py
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from CUZ.core.firebase import db
from fastapi import Header, HTTPException, status


def generate_api_key(role: str, ttl_days: int = 90) -> str:
    """
    Generate a new API key for a given role.
    - Stores only the SHA256 hash in Firestore.
    - Returns the raw key once (to be shown to the admin).
    """
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=ttl_days)

    db.collection("api_keys").document().set({
        "key_hash": key_hash,
        "role": role,
        "created_at": now,
        "expires_at": expires_at,
        "active": True
    })

    return raw_key  # only shown once


def verify_api_key(x_api_key: str = Header(...)) -> str:
    """
    Verify an API key from the request header.
    - Returns the role associated with the key if valid.
    - Raises 401 if invalid, expired, or revoked.
    """
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    docs = db.collection("api_keys") \
             .where("key_hash", "==", key_hash) \
             .where("active", "==", True) \
             .stream()

    for doc in docs:
        data = doc.to_dict()
        if data and data.get("expires_at") > now:
            return data["role"]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired API key"
    )


def rotate_api_key(old_key: str, ttl_days: int = 90) -> str:
    """
    Rotate an API key:
    - Marks the old key as inactive.
    - Issues a new key for the same role.
    - Returns the new raw key (only once).
    """
    old_hash = hashlib.sha256(old_key.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    # Find the old key
    docs = db.collection("api_keys") \
             .where("key_hash", "==", old_hash) \
             .where("active", "==", True) \
             .stream()

    for doc in docs:
        data = doc.to_dict()
        role = data["role"]

        # Mark old key inactive
        doc.reference.update({"active": False})

        # Generate new key for same role
        return generate_api_key(role, ttl_days=ttl_days)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Old API key not found or already inactive"
    )


def ensure_initial_admin_api_key() -> str:
    """
    Ensure at least one admin API key exists.
    If none found, generate a new one and return the raw key.
    """
    docs = db.collection("api_keys").where("role", "==", "admin").stream()
    for doc in docs:
        data = doc.to_dict()
        if data and data.get("active", True):
            # Already have an active admin key
            return None

    # No active admin key found → generate one
    return generate_api_key("admin", ttl_days=90)
