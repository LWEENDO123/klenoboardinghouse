# CUZ/ADMIN/core/bruteforce.py
from datetime import datetime, timedelta, timezone
from CUZ.core.firebase import db

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

MAX_IP_ATTEMPTS = 20
IP_LOCKOUT_MINUTES = 30


# ---------------------------
# Per-account tracking
# ---------------------------
def record_failed_attempt(email: str) -> None:
    doc_ref = db.collection("login_attempts").document(email)
    doc = doc_ref.get()
    now = datetime.now(timezone.utc)

    if doc.exists:
        data = doc.to_dict()
        failed_count = data.get("failed_count", 0) + 1
        if failed_count >= MAX_ATTEMPTS:
            locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            doc_ref.set({
                "failed_count": failed_count,
                "last_failed_at": now,
                "locked_until": locked_until
            })
        else:
            doc_ref.update({
                "failed_count": failed_count,
                "last_failed_at": now
            })
    else:
        doc_ref.set({
            "failed_count": 1,
            "last_failed_at": now,
            "locked_until": None
        })


def is_account_locked(email: str) -> bool:
    doc = db.collection("login_attempts").document(email).get()
    if not doc.exists:
        return False
    data = doc.to_dict()
    locked_until = data.get("locked_until")
    return bool(locked_until and locked_until > datetime.now(timezone.utc))


def reset_attempts(email: str) -> None:
    db.collection("login_attempts").document(email).delete()


# ---------------------------
# Per-IP tracking
# ---------------------------
def record_failed_ip(ip: str) -> None:
    doc_ref = db.collection("ip_attempts").document(ip)
    doc = doc_ref.get()
    now = datetime.now(timezone.utc)

    if doc.exists:
        data = doc.to_dict()
        failed_count = data.get("failed_count", 0) + 1
        if failed_count >= MAX_IP_ATTEMPTS:
            locked_until = now + timedelta(minutes=IP_LOCKOUT_MINUTES)
            doc_ref.set({
                "failed_count": failed_count,
                "last_failed_at": now,
                "locked_until": locked_until
            })
        else:
            doc_ref.update({
                "failed_count": failed_count,
                "last_failed_at": now
            })
    else:
        doc_ref.set({
            "failed_count": 1,
            "last_failed_at": now,
            "locked_until": None
        })


def is_ip_locked(ip: str) -> bool:
    doc = db.collection("ip_attempts").document(ip).get()
    if not doc.exists:
        return False
    data = doc.to_dict()
    locked_until = data.get("locked_until")
    return bool(locked_until and locked_until > datetime.now(timezone.utc))


def reset_ip(ip: str) -> None:
    db.collection("ip_attempts").document(ip).delete()
