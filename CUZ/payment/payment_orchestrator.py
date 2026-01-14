"""
Orchestration layer for payments and payouts.
- Uses Lenco v2.0 function signatures.
- Atomic Firestore logging via transaction wrappers.
- Consolidated, robust polling and consistent schemas.
"""

import uuid
import asyncio
import logging
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional, Dict, Any

# Firestore adapter (atomic wrappers + helpers)
from CUZ.payment.firestore_adapter import (
    get_student_record,
    save_student_record,
    log_gateway_error,
    log_payout_atomic,
    append_payment_idempotent,
)

from CUZ.payment.lenco_gateway import (
    initialize_transfer,
    get_transfer_status,
    initialize_collection,
    get_collection_status,
)



logger = logging.getLogger("payment.orchestrator")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# ------------------------------
# Business rules
# ------------------------------
FULL_PRICE = 5
PROMO_PRICE = 5
PROMO_DISCOUNT_USES = 2
PROMO_WINDOW_MONTHS = 4
REFERRAL_PAYOUT_AMOUNT = 5

# ------------------------------
# Promo decision logic (unchanged)
# ------------------------------
def decide_payment_amount(student_id: str, university: str, promo_code: Optional[str], now: datetime) -> dict:
    """
    Decide the final amount based on promo_code usage and window.
    Writes initial promo window to the student record on first encounter.
    """
    if not promo_code:
        return {"finalAmount": FULL_PRICE, "codeApplied": None, "shouldMarkUsageNow": False}

    student = get_student_record(student_id, university)
    used_codes = set(student.get("used_referral_codes", []))
    usage_list = student.get("promoUsage", [])

    if promo_code not in used_codes:
        expires_at = (now + relativedelta(months=PROMO_WINDOW_MONTHS)).isoformat()
        usage_list.append({
            "code": promo_code,
            "expiresAt": expires_at,
            "discountUsesRemaining": PROMO_DISCOUNT_USES
        })
        student["promoUsage"] = usage_list
        save_student_record(student_id, university, student)
        return {
            "finalAmount": FULL_PRICE,
            "codeApplied": promo_code,
            "shouldMarkUsageNow": True
        }

    for u in usage_list:
        if u["code"] == promo_code:
            try:
                expires = datetime.fromisoformat(u["expiresAt"])
            except Exception:
                break
            if now <= expires and u.get("discountUsesRemaining", 0) > 0:
                return {"finalAmount": PROMO_PRICE, "codeApplied": promo_code, "shouldMarkUsageNow": False}
            break

    return {"finalAmount": FULL_PRICE, "codeApplied": promo_code, "shouldMarkUsageNow": False}

# ------------------------------
# Polling helpers (robust status extraction)
# ------------------------------
async def _poll_collection_status_by_lenco_id(
    lenco_id: str,
    timeout_seconds: int = 30,
    interval_seconds: float = 2.0
) -> Dict[str, Any]:
    elapsed = 0.0
    last_status: Dict[str, Any] = {}
    while elapsed < timeout_seconds:
        try:
            resp = await get_collection_status(lenco_id)
            data = resp.get("data") if isinstance(resp, dict) else resp
            last_status = data or resp
            state = (
                (data.get("status") if isinstance(data, dict) else None) or
                (data.get("state") if isinstance(data, dict) else None) or
                (last_status.get("payment_status") if isinstance(last_status, dict) else None)
            )
            if state and str(state).upper() in {"SUCCESSFUL", "COMPLETED", "SUCCESS", "PAID"}:
                return last_status
            if state and str(state).upper() in {"FAILED", "DECLINED", "ERROR"}:
                return last_status
        except Exception as e:
            logger.debug("[POLL] get_collection_status error: %s", e)
            last_status = {"error": str(e)}
        await asyncio.sleep(interval_seconds)
        elapsed += interval_seconds
    return last_status

async def _poll_transfer_status_by_lenco_id(
    lenco_id: str,
    timeout_seconds: int = 30,
    interval_seconds: float = 2.0
) -> Dict[str, Any]:
    elapsed = 0.0
    last_status: Dict[str, Any] = {}
    while elapsed < timeout_seconds:
        try:
            resp = await get_transfer_status(lenco_id)
            data = resp.get("data") if isinstance(resp, dict) else resp
            last_status = data or resp
            state = (
                (data.get("status") if isinstance(data, dict) else None) or
                (data.get("state") if isinstance(data, dict) else None) or
                (last_status.get("transfer_status") if isinstance(last_status, dict) else None)
            )
            if state and str(state).upper() in {"SUCCESSFUL", "COMPLETED", "SUCCESS"}:
                return last_status
            if state and str(state).upper() in {"FAILED", "DECLINED", "ERROR"}:
                return last_status
        except Exception as e:
            logger.debug("[POLL] get_transfer_status error: %s", e)
            last_status = {"error": str(e)}
        await asyncio.sleep(interval_seconds)
        elapsed += interval_seconds
    return last_status

# ------------------------------
# Unified payout orchestration (atomic)
# ------------------------------
async def process_payout(
    university: str,
    union_id: str,
    referral_code: str,
    student_id: str,
    msisdn: str,
    amount: float = REFERRAL_PAYOUT_AMOUNT,
    provider_hint: Optional[str] = None,
    poll_timeout_seconds: int = 30,
    poll_interval_seconds: float = 2.0
) -> Dict[str, Any]:
    """
    Orchestrate a payout via mobile money:
      1) Initialize transfer
      2) Poll until final status
      3) Atomically log payout + referral usage + notification
    """
    now = datetime.utcnow()
    reference = f"payout-{union_id}-{uuid.uuid4().hex[:12]}"

    try:
        logger.info("[ORCH] Initializing transfer: union=%s university=%s amount=%s msisdn=%s", union_id, university, amount, msisdn)
        init_resp = await initialize_transfer(
            amount=str(amount),
            currency="ZMW",
            provider=provider_hint or "airtel",
            phone_number=msisdn,
            reference=reference,
            narration="KLENO referral payout",
            idempotency_key=None,
        )
        logger.debug("[ORCH] Lenco initialize_transfer response: %s", init_resp)

        lenco_id = None
        if isinstance(init_resp, dict):
            data = init_resp.get("data")
            if isinstance(data, dict):
                lenco_id = data.get("id")
            lenco_id = lenco_id or init_resp.get("id")

        final_status = {}
        if lenco_id:
            final_status = await _poll_transfer_status_by_lenco_id(
                lenco_id,
                timeout_seconds=poll_timeout_seconds,
                interval_seconds=poll_interval_seconds
            )

        transaction_id = (final_status or {}).get("id") or lenco_id
        status = (final_status or {}).get("status") or "PENDING"

        # ✅ Atomic Firestore logging
        payout_data = {
            "reference": reference,
            "initializeResponse": init_resp,
            "finalStatus": final_status
        }
        log_payout_atomic(
            university=university,
            union_id=union_id,
            referral_code=referral_code,
            student_id=student_id,
            payout_id=transaction_id,
            payout_status=status,
            payout_data=payout_data
        )

        return {
            "ok": True,
            "payout": {
                "id": transaction_id,
                "status": status,
                "reference": reference,
                "initializeResponse": init_resp,
                "finalStatus": final_status
            }
        }

    except Exception as e:
        logger.exception("[ORCH] Payout orchestration error")
        log_gateway_error({
            "unionId": union_id,
            "error": str(e),
            "timestamp": now.isoformat()
        })
        return {"ok": False, "error": str(e)}

# ------------------------------
# Optional: direct collection orchestration (if needed)
# Prefer the gateway endpoint /collect/mobile-money for actual use.
# ------------------------------
async def process_collection(
    student_id: str,
    university: str,
    msisdn: str,
    amount: float,
    provider_hint: Optional[str] = None,
    poll_timeout_seconds: int = 30,
    poll_interval_seconds: float = 2.0
) -> Dict[str, Any]:
    """
    Orchestrate a direct mobile money collection:
      1) Initialize collection
      2) Poll until final status
      3) Append payment idempotently (non-atomic)
    Note: For atomic logging, prefer using the gateway route with log_collection_atomic.
    """
    try:
        prov = (provider_hint or "airtel").lower()
        reference = f"student-{student_id}-{uuid.uuid4().hex[:12]}"

        init = await initialize_collection(
            amount=str(amount),
            currency="ZMW",
            provider=prov,
            phone_number=msisdn,
            reference=reference,
            narration="KLENO premium subscription",
            metadata={"student_id": student_id, "university": university},
            idempotency_key=None
        )

        lenco_id = None
        if isinstance(init, dict):
            data = init.get("data")
            if isinstance(data, dict):
                lenco_id = data.get("id")
            lenco_id = lenco_id or init.get("id")

        final_status = {}
        if lenco_id:
            final_status = await _poll_collection_status_by_lenco_id(
                lenco_id,
                timeout_seconds=poll_timeout_seconds,
                interval_seconds=poll_interval_seconds
            )

        status = (final_status or {}).get("status") or "PENDING"

        # Non-atomic summary append (kept for compatibility)
        append_payment_idempotent(
            student_id=student_id,
            university=university,
            transaction_id=lenco_id or reference,
            payment={
                "amount": amount,
                "status": status,
                "reference": reference,
                "operator": prov,
                "loggedAt": datetime.utcnow().isoformat(),
            }
        )

        return {
            "ok": True,
            "collection": {
                "id": lenco_id,
                "status": status,
                "reference": reference,
                "initializeResponse": init,
                "finalStatus": final_status
            }
        }

    except Exception as e:
        logger.exception("[ORCH] Collection orchestration error")
        log_gateway_error({"error": str(e), "timestamp": datetime.utcnow().isoformat()})
        return {"ok": False, "error": str(e)}

        return {"ok": False, "error": str(e)}

# ------------------------------
# Premium expiry check (unchanged)
# ------------------------------
def check_and_update_premium_expiry():
    from google.cloud import firestore
    now = datetime.utcnow()

    universities = firestore.Client().collection("USERS").stream()

    for uni_doc in universities:
        university = uni_doc.id
        students = firestore.Client().collection("USERS").document(university).collection("students").stream()

        for doc in students:
            student_id = doc.id
            student = doc.to_dict()

            expiry_str = student.get("premiumExpiresAt")
            if not expiry_str:
                continue

            try:
                expiry = datetime.fromisoformat(expiry_str)
            except Exception:
                continue

            if now > expiry:
                student["premium"] = False
                student["premiumExpiredAt"] = now.isoformat()
                save_student_record(student_id, university, student)
