# CUZ/ADMIN/core/cleanup
from datetime import datetime, timezone, timedelta
from CUZ.core.firebase import db

def cleanup_expired_tokens():
    """
    Delete expired refresh tokens from Firestore.
    """
    now = datetime.now(timezone.utc)
    tokens_ref = db.collection("refresh_tokens")
    expired_tokens = tokens_ref.where("expires_at", "<", now.isoformat()).stream()

    batch = db.batch()
    count = 0
    for doc in expired_tokens:
        batch.delete(doc.reference)
        count += 1
        if count >= 400:  # Firestore batch limit
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()


def cleanup_expired_api_keys():
    """
    Delete expired API keys from Firestore.
    """
    now = datetime.now(timezone.utc)
    keys_ref = db.collection("API_KEYS")
    expired_keys = keys_ref.where("expires_at", "<", now.isoformat()).stream()

    batch = db.batch()
    count = 0
    for doc in expired_keys:
        batch.delete(doc.reference)
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()


def cleanup_old_audit_logs(retention_days: int = 90):
    """
    Delete audit logs older than retention_days (default: 90 days).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    logs_ref = db.collection("audit_logs").where("timestamp", "<", cutoff.isoformat()).stream()

    batch = db.batch()
    count = 0
    for doc in logs_ref:
        batch.delete(doc.reference)
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()
