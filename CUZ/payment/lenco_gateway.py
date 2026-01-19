# file: C:\Users\lweendo\project\baodinghouse\CUZ\payment\lenco_gateway.py
"""
Lenco gateway (production-ready, async).
- Uses the account info you supplied (hard-coded as requested).
- Low-level functions:
    initialize_collection, get_collection_status,
    initialize_transfer, get_transfer_status
- High-level helpers: collect_payment, payout
- Webhook signature verification helper: verify_lenco_signature
- Exposes a FastAPI router for manual testing: POST /payments/collect
Notes:
- This implementation uses x-api-key header (Lenco expects API key header).
- Idempotency header is provided for init calls.
- Provider auto-detection is implemented via prefix map; falls back to 'airtel'.
"""
from CUZ.payment.firestore_adapter import log_collection_atomic
from datetime import datetime
from google.cloud import firestore
from CUZ.core.firebase import db
import json
import uuid
import logging
import asyncio
import hmac
import hashlib
from typing import Dict, Any, Optional, Tuple

import httpx
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel
import os
from pydantic import BaseModel
from typing import Optional


router = APIRouter(prefix="/payments", tags=["payments"])


# ----------------------
# Logging
# ----------------------
logger = logging.getLogger("payment.lenco_v2")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

# ----------------------
# Hard-coded config (as requested)
# Replace these in future with env vars / secrets manager.
# ----------------------
# CUZ/payment/lenco_config.py



# ==============================
# Lenco API Settings
# ==============================

LENCO_API_KEY = os.getenv("LENCO_API_KEY")  # secret (dashboard)
LENCO_PUBLIC_API_KEY = os.getenv("LENCO_PUBLIC_API_KEY")  # public key
LENCO_WEBHOOK_SIGNATURE_KEY = os.getenv("LENCO_WEBHOOK_SIGNATURE_KEY")  # webhook signature key (hex)

# Base URL from your dashboard (includes /access/v2)
LENCO_BASE_URL = os.getenv("LENCO_BASE_URL", "https://api.lenco.co/access/v2")


# timeouts
TIMEOUT = 30

# Default request headers. We include x-api-key (primary) and Authorization Bearer for compatibility.
DEFAULT_HEADERS = {
    "x-api-key": LENCO_API_KEY,
    "Authorization": f"Bearer {LENCO_API_KEY}",  # keep for compatibility with older examples; Lenco primarily uses x-api-key
    "Content-Type": "application/json",
}

_client = httpx.AsyncClient(base_url=LENCO_BASE_URL, headers=DEFAULT_HEADERS, timeout=TIMEOUT)

# Allowed providers
ALLOWED_PROVIDERS = {"airtel", "mtn", "zamtel"}

# ----------------------
# Provider autodetection config
# Add or edit prefixes as you discover carrier ranges for your region.
# Format: prefix (string) -> provider (string)
# These are for common Zambian mobile prefixes — adjust if you have accurate lists.
# NOTE: Keep conservative and fall back to 'airtel' if unknown.
# ----------------------
_PROVIDER_PREFIX_MAP = {
    # Airtel common prefixes (example)
    "097": "airtel",
    #"095": "airtel",
    #"078": "airtel",
    # MTN common prefixes (example)
    "096": "mtn",
    #"088": "mtn",
    # Zamtel common prefixes (example)
    #"076": "zamtel",
    "095": "zamtel",
}

def _detect_provider_from_msisdn(msisdn: str) -> str:
    """
    Try to detect provider from msisdn. Accepts local formats like:
    - 0971234567
    - 260971234567 (country code)
    - +260971234567
    Returns one of ALLOWED_PROVIDERS, defaults to 'airtel'.
    """
    if not msisdn:
        return "airtel"
    s = msisdn.strip()
    # remove leading +
    if s.startswith("+"):
        s = s[1:]
    # remove leading country code (common for Zambia = 260)
    if s.startswith("260") and len(s) > 3:
        # take the next 3 digits as prefix
        s_local = s[3:]
    else:
        s_local = s

    # take first 3 digits as prefix candidate
    prefix = s_local[:3]
    provider = _PROVIDER_PREFIX_MAP.get(prefix)
    if provider and provider in ALLOWED_PROVIDERS:
        return provider
    # fallback: try first 2 digits
    prefix2 = s_local[:2]
    for k, v in _PROVIDER_PREFIX_MAP.items():
        if k.startswith(prefix2) and v in ALLOWED_PROVIDERS:
            return v
    return "airtel"

# ----------------------
# Utilities
# ----------------------
def _idempotency_key(prefix: str = "kleno") -> str:
    return f"{prefix}-{uuid.uuid4().hex}"

def _safe_json(resp: httpx.Response) -> Any:
    """Return parsed json or text if JSON fails."""
    try:
        return resp.json()
    except Exception:
        return resp.text


# ----------------------
# Webhook signature verification
# ----------------------
def verify_lenco_signature(signature_header: Optional[str], payload_bytes: bytes) -> bool:
    """
    Verify Lenco webhook signature using HMAC-SHA256.
    - signature_header: raw header value; supports forms like:
        "sha256=<hex>" or raw hex string
    - payload_bytes: raw request body bytes
    Returns True if signature matches.
    """
    if not signature_header:
        logger.debug("[Lenco Signature] No signature header provided")
        return False

    # try to interpret provided webhook key as hex; fallback to raw bytes
    try:
        secret = bytes.fromhex(LENCO_WEBHOOK_SIGNATURE_KEY)
    except Exception:
        secret = LENCO_WEBHOOK_SIGNATURE_KEY.encode("utf-8")

    mac = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    header = signature_header.strip()
    if header.startswith("sha256="):
        header_val = header.split("=", 1)[1]
    else:
        header_val = header

    valid = hmac.compare_digest(mac, header_val)
    if not valid:
        logger.warning("[Lenco Signature] signature mismatch (computed=%s header=%s)", mac, header_val)
    return valid

# ----------------------
# Low-level Lenco v2 functions (async)
# ----------------------
async def initialize_collection(
    amount: str,
    currency: str,
    provider: str,
    phone_number: str,
    reference: str,
    narration: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:

    """
    POST /collections/mobile-money
    - amount: string or numeric value
    - provider: airtel, mtn, zamtel
    - phone: MSISDN in +260 format
    - country: 'zm'
    - bearer: who bears the cost ('merchant' or 'customer')
    """
    prov = (provider or "airtel").lower()
    if prov not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{prov}'")

    if idempotency_key is None:
        idempotency_key = _idempotency_key("collection")

    payload = {
        "operator": prov,
        "bearer": "merchant",   # default: merchant pays fees
        "phone": phone_number,
        "amount": str(amount),
        "country": "zm",
        "reference": reference,
    }
    if narration:
        payload["narration"] = narration
    if metadata:
        payload["metadata"] = metadata

    logger.info("[Lenco] initialize_collection reference=%s provider=%s amount=%s", reference, prov, amount)

    headers = {
        "Idempotency-Key": idempotency_key,
        "x-api-key": LENCO_API_KEY,
        "Content-Type": "application/json",
    }
    try:
        resp = await _client.post("/collections/mobile-money", json=payload, headers=headers)
    except httpx.RequestError as e:
        logger.exception("[Lenco] request error initialize_collection")
        raise HTTPException(status_code=503, detail=f"Lenco request error: {str(e)}")

    body = _safe_json(resp)
    if resp.status_code >= 400:
        logger.error("[Lenco] initialize_collection error %s %s", resp.status_code, body)
        raise HTTPException(status_code=resp.status_code, detail=body)

    return body

async def get_collection_status(collection_id: str) -> Dict[str, Any]:
    """
    GET /collections/{id}
    """
    logger.debug("[Lenco] get_collection_status id=%s", collection_id)
    headers = {"x-api-key": LENCO_API_KEY, "Content-Type": "application/json"}
    try:
        resp = await _client.get(f"/collections/{collection_id}", headers=headers)
    except httpx.RequestError as e:
        logger.exception("[Lenco] request error get_collection_status")
        raise HTTPException(status_code=503, detail=f"Lenco request error: {str(e)}")

    body = _safe_json(resp)
    if resp.status_code >= 400:
        logger.error("[Lenco] get_collection_status error %s %s", resp.status_code, body)
        raise HTTPException(status_code=resp.status_code, detail=body)

    return body


async def initialize_transfer(
    amount: str,
    currency: str,
    provider: str,
    phone_number: str,
    reference: str,
    narration: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    POST /transfers
    """
    prov = (provider or "airtel").lower()
    if prov not in ALLOWED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider '{prov}'")

    if idempotency_key is None:
        idempotency_key = _idempotency_key("transfer")

    payload = {
        "amount": str(amount),
        "currency": currency,
        "provider": prov,
        "phone_number": phone_number,
        "reference": reference,
    }
    if narration:
        payload["narration"] = narration

    logger.info("[Lenco] initialize_transfer reference=%s provider=%s amount=%s", reference, prov, amount)
    headers = {"Idempotency-Key": idempotency_key, "x-api-key": LENCO_API_KEY}
    try:
        resp = await _client.post("/transfers", json=payload, headers=headers)
    except httpx.RequestError as e:
        logger.exception("[Lenco] request error initialize_transfer")
        raise HTTPException(status_code=503, detail=f"Lenco request error: {str(e)}")

    if resp.status_code >= 400:
        body = _safe_json(resp)
        logger.error("[Lenco] initialize_transfer error %s %s", resp.status_code, body)
        raise HTTPException(status_code=resp.status_code, detail=body)

    return _safe_json(resp)

async def get_transfer_status(transfer_id: str) -> Dict[str, Any]:
    """
    GET /transfers/{id}
    """
    logger.debug("[Lenco] get_transfer_status id=%s", transfer_id)
    headers = {"x-api-key": LENCO_API_KEY}
    try:
        resp = await _client.get(f"/transfers/{transfer_id}", headers=headers)
    except httpx.RequestError as e:
        logger.exception("[Lenco] request error get_transfer_status")
        raise HTTPException(status_code=503, detail=f"Lenco request error: {str(e)}")

    if resp.status_code >= 400:
        body = _safe_json(resp)
        logger.error("[Lenco] get_transfer_status error %s %s", resp.status_code, body)
        raise HTTPException(status_code=resp.status_code, detail=body)

    return _safe_json(resp)

# ----------------------
# High-level wrappers (preserve your existing logic)
# ----------------------
async def collect_payment(student_id: str, university: str, msisdn: str,
                          amount: float, provider: Optional[str] = None,
                          poll: bool = True, poll_timeout_seconds: int = 30,
                          poll_interval_seconds: float = 2.0) -> Dict[str, Any]:
    """
    High-level convenience to create a collection and optionally poll until final status.
    If provider is None, we attempt to auto-detect from msisdn.
    """
    prov = provider or _detect_provider_from_msisdn(msisdn)
    if prov not in ALLOWED_PROVIDERS:
        prov = "airtel"

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

    # parse lenco internal id robustly
    lenco_id = None
    if isinstance(init, dict):
        data = init.get("data")
        if isinstance(data, dict):
            lenco_id = data.get("id")
        lenco_id = lenco_id or init.get("id")

    result = {"reference": reference, "initialize": init, "lenco_id": lenco_id}

    elapsed = 0.0
    while poll and elapsed < poll_timeout_seconds and lenco_id:
        try:
            status_resp = await get_collection_status(lenco_id)
        except Exception as e:
            logger.debug("[Lenco Poll] get_collection_status error: %s", e)
            result["latest_status"] = {"error": str(e)}
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
            continue

        st = status_resp.get("data") if isinstance(status_resp, dict) else status_resp
        result["latest_status"] = st
        state = None
        if isinstance(st, dict):
            state = st.get("status") or st.get("state") or st.get("payment_status")

        if state and str(state).upper() in {"SUCCESSFUL", "COMPLETED", "SUCCESS", "PAID"}:
            result["final_status"] = st
            return result
        if state and str(state).upper() in {"FAILED", "DECLINED", "ERROR"}:
            result["final_status"] = st
            return result

        await asyncio.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds

    return result

async def payout(union_id: str, university: str, msisdn: str, amount: float,
                 provider: Optional[str] = None,
                 poll: bool = True, poll_timeout_seconds: int = 30,
                 poll_interval_seconds: float = 2.0) -> Dict[str, Any]:
    """
    High-level transfer / payout helper. Auto-detects provider if not supplied.
    """
    prov = provider or _detect_provider_from_msisdn(msisdn)
    if prov not in ALLOWED_PROVIDERS:
        prov = "airtel"

    reference = f"payout-{union_id}-{uuid.uuid4().hex[:12]}"

    init = await initialize_transfer(
        amount=str(amount),
        currency="ZMW",
        provider=prov,
        phone_number=msisdn,
        reference=reference,
        narration="KLENO referral payout",
        idempotency_key=None,
    )

    transfer_id = None
    if isinstance(init, dict):
        data = init.get("data")
        if isinstance(data, dict):
            transfer_id = data.get("id")
        transfer_id = transfer_id or init.get("id")

    result = {"reference": reference, "initialize": init, "lenco_id": transfer_id}
    elapsed = 0.0
    while poll and elapsed < poll_timeout_seconds and transfer_id:
        try:
            status_resp = await get_transfer_status(transfer_id)
        except Exception as e:
            logger.debug("[Lenco Poll] get_transfer_status error: %s", e)
            result["latest_status"] = {"error": str(e)}
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
            continue

        st = status_resp.get("data") if isinstance(status_resp, dict) else status_resp
        result["latest_status"] = st
        state = None
        if isinstance(st, dict):
            state = st.get("status") or st.get("state") or st.get("transfer_status")

        if state and str(state).upper() in {"SUCCESSFUL", "COMPLETED", "SUCCESS"}:
            result["final_status"] = st
            return result
        if state and str(state).upper() in {"FAILED", "DECLINED", "ERROR"}:
            result["final_status"] = st
            return result

        await asyncio.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds

    return result

# ----------------------
# Compatibility exports (names expected by orchestrator)
# ----------------------
initialize_collection = initialize_collection
get_collection_status = get_collection_status
initialize_transfer = initialize_transfer
get_transfer_status = get_transfer_status
# ----------------------
# ----------------------
# Mobile Money Collection (low-level helper)
# ----------------------
async def initialize_mobile_money_collection(
    payload: Dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    POST /collections/mobile-money
    Expects full payload dict with:
      - operator: airtel, mtn, zamtel
      - bearer: who bears the cost ('merchant' or 'customer')
      - phone: MSISDN in +260 format
      - amount: numeric value
      - country: e.g. 'zm'
      - reference: unique external reference
    """
    if idempotency_key is None:
        idempotency_key = _idempotency_key("mobile-money")

    logger.info(f"[Lenco] initialize_mobile_money_collection payload={json.dumps(payload)}")

    headers = {
        "Idempotency-Key": idempotency_key,
        "x-api-key": LENCO_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = await _client.post("/collections/mobile-money", json=payload, headers=headers)
    except httpx.RequestError as e:
        logger.exception("[Lenco] request error initialize_mobile_money_collection")
        raise HTTPException(status_code=503, detail=f"Lenco request error: {str(e)}")

    body = _safe_json(resp)
    logger.info(f"[Lenco] response status={resp.status_code} body={body}")

    if resp.status_code >= 400:
        logger.error("[Lenco] initialize_mobile_money_collection error %s %s", resp.status_code, body)
        raise HTTPException(status_code=resp.status_code, detail=body)

    return body


# ----------------------
# FastAPI Router for manual testing
# ----------------------


# This one is no longer needed since /collect was removed,
# but if you want to keep it for reference/testing you can.
class CollectRequest(BaseModel):
    student_id: str
    university: str
    msisdn: str
    amount: float
    provider: Optional[str] = None
    poll_timeout_seconds: Optional[int] = 30
    poll_interval_seconds: Optional[float] = 2.0

class PayoutRequest(BaseModel):
    university: str
    union_id: str
    student_id: str
    msisdn: str
    referral_code: str   # ✅ new field for atomic logging
    amount: float = 20.0
    provider: Optional[str] = None
    poll_timeout_seconds: Optional[int] = 30
    poll_interval_seconds: Optional[float] = 2.0

class MobileMoneyRequest(BaseModel):
    university: str      # ✅ new field so logging uses correct Firestore path
    operator: str
    bearer: Optional[str] = "merchant"
    phone: str
    amount: float = 75
    country: str = "zm"
    poll_timeout_seconds: Optional[int] = 30
    poll_interval_seconds: Optional[float] = 2.0



# Utility: normalize phone numbers to +260 format
def _normalize_msisdn(msisdn: str) -> str:
    if not msisdn:
        return msisdn
    s = msisdn.strip()
    if s.startswith("+"):
        return s
    if s.startswith("260"):
        return f"+{s}"
    if s.startswith("0"):
        return f"+260{s[1:]}"
    return f"+260{s}"

# ----------------------
# Payout endpoint
# ----------------------
@router.post("/payout")
async def route_payout(req: PayoutRequest):
    """
    Initiate a payout (disbursement) via mobile money.
    Flow:
      1. Create transfer recipient (mobile money)
      2. Initialize transfer to that recipient
      3. Poll until final status
      4. Log payout + referral usage + notification atomically in Firestore
    """
    try:
        normalized_msisdn = _normalize_msisdn(req.msisdn)

        # Step 1: create recipient
        recipient_payload = {
            "operator": req.provider.lower() if req.provider else _detect_provider_from_msisdn(normalized_msisdn),
            "phone": normalized_msisdn,
            "country": "zm"
        }
        recipient_resp = await _client.post(
            "/transfer-recipients/mobile-money",
            json=recipient_payload,
            headers={"x-api-key": LENCO_API_KEY, "Content-Type": "application/json"}
        )
        recipient_body = _safe_json(recipient_resp)
        if recipient_resp.status_code >= 400:
            raise HTTPException(status_code=recipient_resp.status_code, detail=recipient_body)

        recipient_id = recipient_body.get("data", {}).get("id")
        if not recipient_id:
            raise HTTPException(status_code=500, detail="Failed to create transfer recipient")

        # Step 2: initialize transfer
        reference = f"payout-{req.union_id}-{uuid.uuid4().hex[:12]}"
        transfer_payload = {
            "amount": str(req.amount),
            "currency": "ZMW",
            "recipient": recipient_id,
            "reference": reference,
            "narration": "KLENO referral payout"
        }
        transfer_resp = await _client.post(
            "/transfers",
            json=transfer_payload,
            headers={"x-api-key": LENCO_API_KEY, "Content-Type": "application/json"}
        )
        transfer_body = _safe_json(transfer_resp)
        if transfer_resp.status_code >= 400:
            raise HTTPException(status_code=transfer_resp.status_code, detail=transfer_body)

        transfer_id = transfer_body.get("data", {}).get("id") or transfer_body.get("id")
        result = {"reference": reference, "initialize": transfer_body, "lenco_id": transfer_id}

        # Step 3: poll until final status
        elapsed = 0.0
        poll_timeout_seconds = req.poll_timeout_seconds or 30
        poll_interval_seconds = req.poll_interval_seconds or 2.0

        final_status = {}
        while elapsed < poll_timeout_seconds and transfer_id:
            try:
                status_resp = await get_transfer_status(transfer_id)
                st = status_resp.get("data") if isinstance(status_resp, dict) else status_resp
                final_status = st or {}
                state = final_status.get("status") or final_status.get("state") or final_status.get("transfer_status")
                if state and str(state).upper() in {"SUCCESSFUL", "COMPLETED", "SUCCESS", "FAILED", "DECLINED", "ERROR"}:
                    break
            except Exception as e:
                result["latest_status"] = {"error": str(e)}
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds

        # Step 4: atomic Firestore logging
        from payment.firestore_adapter import log_payout_atomic
        payout_data = {
            "reference": reference,
            "initializeResponse": transfer_body,
            "finalStatus": final_status
        }
        # Note: make sure your PayoutRequest model includes referral_code
        log_payout_atomic(
            req.university,
            req.union_id,
            req.referral_code,   # ✅ pass actual referral code, not union_id
            req.student_id,
            transfer_id,
            final_status.get("status", "PENDING"),
            payout_data
        )

        return {
            "status": final_status.get("status") in {"SUCCESSFUL", "COMPLETED", "SUCCESS"},
            "message": f"Payout {final_status.get('status', 'PENDING')}",
            "data": result
        }

    except Exception as e:
        logger.error(f"[Payout] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Payout failed: {str(e)}")


# ----------------------
# Mobile money collection endpoint (only one kept)
# ----------------------
@router.post("/collect/mobile-money")
async def route_mobile_money(req: MobileMoneyRequest):
    """
    Initiate a mobile money collection.
    Sends payload to Lenco, polls until final status,
    and logs payment atomically in Firestore.
    """
    try:
        normalized_phone = _normalize_msisdn(req.phone)
        payload = {
            "operator": req.operator.lower(),
            "bearer": req.bearer.lower(),
            "phone": normalized_phone,
            "amount": req.amount,
            "country": req.country.lower(),
            "reference": f"mobile-{uuid.uuid4().hex[:12]}"
        }

        init = await initialize_mobile_money_collection(payload)
        lenco_id = init.get("id") or init.get("data", {}).get("id")
        result = {"initialize": init, "lenco_id": lenco_id}

        elapsed = 0.0
        poll_timeout_seconds = req.poll_timeout_seconds or 30
        poll_interval_seconds = req.poll_interval_seconds or 2.0

        final_status = {}
        while elapsed < poll_timeout_seconds and lenco_id:
            try:
                status_resp = await get_collection_status(lenco_id)
                st = status_resp.get("data") if isinstance(status_resp, dict) else status_resp
                final_status = st or {}
                state = final_status.get("status") or final_status.get("state") or final_status.get("payment_status")
                if state and str(state).upper() in {"SUCCESSFUL", "COMPLETED", "SUCCESS", "PAID", "FAILED", "DECLINED", "ERROR"}:
                    break
            except Exception as e:
                result["latest_status"] = {"error": str(e)}
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds

        # ✅ Atomic Firestore logging
        
        log_collection_atomic(
            req.student_id,
            req.university,   # ✅ use university, not country
            lenco_id,
            req.amount,
            final_status.get("status", "PENDING"),
            payload["operator"],
            payload["reference"]
        )

        return {
            "status": final_status.get("status") in {"SUCCESSFUL", "COMPLETED", "SUCCESS", "PAID"},
            "message": f"Mobile money collection {final_status.get('status', 'PENDING')}",
            "data": {
                "reference": payload["reference"],
                "lenco_id": lenco_id,
                "final_status": final_status
            }
        }

    except Exception as e:
        logger.error(f"[MobileMoney] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Mobile money collection failed: {str(e)}")




logger = logging.getLogger("users.phone")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.DEBUG)




# Reuse db from core.firebase or firestore_adapter
# db = firestore.Client(...)

def get_student_record(student_id: str, university: str) -> dict:
    """
    Fetch student record from Firestore under /USERS/{university}/students/{student_id}.
    Returns dict with defaults if not found.
    """
    logger.debug(f"Looking up student_id={student_id} in university={university}")
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        logger.debug(f"Document found: {data}")
        return data
    else:
        logger.warning(f"No document found at USERS/{university}/students/{student_id}")
        return {
            "phone_number": None,
            "msisdn": None,
            "payments": [],
            "used_referral_codes": [],
            "premium": False,
        }

@router.get("/{student_id}/phone")
async def get_student_phone(student_id: str, university: str):
    """
    Return the registered phone number for a student.
    Adds normalization, timestamp, and consistent schema.
    """
    logger.info(f"Fetching phone for student_id={student_id}, university={university}")
    student = get_student_record(student_id, university)

    phone = student.get("phone_number")
    if not phone:
        logger.error(f"Phone number not found for id={student_id}, university={university}")
        raise HTTPException(status_code=404, detail="Phone number not found")

    # Normalize to +260 format
    normalized_phone = _normalize_msisdn(phone)

    # Build response with audit fields
    response = {
        "phone_number": normalized_phone,
        "source": "stored",
        "student_id": student_id,
        "university": university,
        "timestamp": datetime.utcnow().isoformat(),
    }

    logger.info(f"Returning phone_number={normalized_phone} for student_id={student_id}, university={university}")
    return response

@router.get("/debug")
async def payments_debug():
    return {"ok": True, "msg": "payments router is active"}

  
