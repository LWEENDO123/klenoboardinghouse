# CUZ/ADMIN/core/alert_checker.py
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from CUZ.core.firebase import db

MFA_FAIL_THRESHOLD = 3
AUTH_FAIL_THRESHOLD = 10
WINDOW_MINUTES = 5

def check_recent_events():
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=WINDOW_MINUTES)

    logs_ref = db.collection("audit_logs").where("timestamp", ">=", window_start.isoformat())
    logs = [doc.to_dict() for doc in logs_ref.stream()]

    alerts = []

    # Group auth failures by IP
    auth_failures_by_ip = defaultdict(list)
    for log in logs:
        if log["action"] == "auth_failure":
            auth_failures_by_ip[log.get("ip", "unknown")].append(log)

    # MFA failures
    mfa_failures = [l for l in logs if l["action"] == "mfa_verification_failed"]
    if len(mfa_failures) >= MFA_FAIL_THRESHOLD:
        alerts.append(f"⚠️ MFA failures: {len(mfa_failures)} in last {WINDOW_MINUTES} minutes")

    # Auth failures grouped by IP
    for ip, failures in auth_failures_by_ip.items():
        if len(failures) >= AUTH_FAIL_THRESHOLD:
            alerts.append(f"🚨 {len(failures)} auth failures from IP {ip} in last {WINDOW_MINUTES} minutes")

    # Token reuse
    token_reuse = [l for l in logs if l["action"] == "refresh_token_reuse_detected"]
    for event in token_reuse:
        alerts.append(f"🚨 Token reuse detected for actor={event['actor']} at {event['ip']}")

    return alerts

def run_alert_check():
    alerts = check_recent_events()
    if alerts:
        for a in alerts:
            # Replace with email/SMS/Slack integration
            print(a)
    else:
        print("✅ No suspicious activity detected")
