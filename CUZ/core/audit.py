# CUZ/ADMIN/core/audit.py
from datetime import datetime, timezone
import uuid
from CUZ.core.firebase import db   # or swap with SQLAlchemy if using Postgres

def log_event(
    actor: str,
    action: str,
    role: str = None,
    ip: str = None,
    user_agent: str = None,
    category: str = "system",
    severity: str = "INFO",
    metadata: dict = None
):
    """
    Generic audit logger.
    Stores structured events in Firestore under audit_logs/{log_id}.
    """
    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db.collection("audit_logs").document(log_id).set({
        "actor": actor,
        "action": action,
        "role": role,
        "ip": ip,
        "user_agent": user_agent,
        "category": category,       # e.g., auth, mfa, token, system
        "severity": severity,       # INFO, WARN, ERROR
        "timestamp": now.isoformat(),
        "metadata": metadata or {}
    })


# -----------------------------
# Helper functions for security
# -----------------------------

def log_failed_mfa(actor: str, ip: str, user_agent: str):
    log_event(
        actor=actor,
        action="mfa_verification_failed",
        category="mfa",
        severity="WARN",
        ip=ip,
        user_agent=user_agent
    )

def log_token_reuse(actor: str, jti: str, ip: str, user_agent: str):
    log_event(
        actor=actor,
        action="refresh_token_reuse_detected",
        category="token",
        severity="ERROR",
        ip=ip,
        user_agent=user_agent,
        metadata={"jti": jti}
    )

def log_ip_ua_mismatch(actor: str, expected_ip: str, expected_ua: str, ip: str, user_agent: str):
    log_event(
        actor=actor,
        action="ip_ua_mismatch",
        category="token",
        severity="ERROR",
        ip=ip,
        user_agent=user_agent,
        metadata={"expected_ip": expected_ip, "expected_ua": expected_ua}
    )

def log_auth_failure(actor: str, ip: str, user_agent: str, reason: str):
    log_event(
        actor=actor,
        action="auth_failure",
        category="auth",
        severity="WARN",
        ip=ip,
        user_agent=user_agent,
        metadata={"reason": reason}
    )
