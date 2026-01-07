
# file: C:\Users\lweendo\project\baodinghouse\CUZ\main.py
from fastapi import FastAPI, Depends, Request, APIRouter, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
# Import the unified event router
from CUZ.yearbook.profile.events import router as event_router



# Import the notification router and the notify_upcoming_events function
from CUZ.Notification.notification import router as notification_router
from CUZ.Notification.notification import notify_upcoming_events

from USERS.user_routes import router as user_router, get_current_user







from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Standard libs
import logging
import hmac
import hashlib
from datetime import datetime
from dateutil.relativedelta import relativedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel, constr

# Routers & dependencies (existing in your project)
from USERS.user_routes import router as user_router
from USERS.Appkey import verify_api_key
from Available.check_boarding import router as available_router

from Notification.notification import router as notification_router
from PINNED.pinned import router as pinned_router
from PINNED import user_routes as pinned_user_routes
from HOME.add_boardinghouse import router as boardinghouse_router
from HOME.user_routes import router as user_home_router
from Store.store import router as store_router
from ProxyLocation.fine_me import router as proxily_router

# Payment modules
from payment.firestore_adapter import get_student_record, save_student_record
from payment.lenco_gateway import router as lenco_router
from payment.payment_orchestrator import (
    check_and_update_premium_expiry,
     process_payout
)

# Firebase + security
from core.firebase import db  # ensures firebase initialized
import core.security
from ADMIN.api_keys_bootstrap import ensure_initial_admin_api_key

# App initialization
app = FastAPI(title="Baodinghouse API")

# routers
debug_router = APIRouter(prefix="/debug", tags=["debug"])
webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])

# Logging setup
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

# Debug route
@debug_router.post("/headers")
async def debug_headers(request: Request):
    return {
        "authorization": request.headers.get("authorization"),
        "x_api_key": request.headers.get("x-api-key"),
        "host": request.headers.get("host"),
    }

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in prod if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key dependency
auth_dependency = Depends(verify_api_key)

# Rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["1000/hour"])
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down.",
            "limit": str(exc.detail),
            "retry_after_seconds": exc.reset_in,
        },
    )
    response.headers["Retry-After"] = str(exc.reset_in)
    return response


# Router includes (preserve your original structure)
app.include_router(debug_router)
app.include_router(user_router, dependencies=[auth_dependency])
app.include_router(user_home_router, dependencies=[auth_dependency])
app.include_router(pinned_router, dependencies=[auth_dependency])
app.include_router(pinned_user_routes.router, dependencies=[auth_dependency])
app.include_router(available_router, dependencies=[auth_dependency])
app.include_router(event_router, dependencies=[auth_dependency])
app.include_router(notification_router, dependencies=[auth_dependency])
app.include_router(boardinghouse_router, dependencies=[auth_dependency])
app.include_router(store_router, dependencies=[auth_dependency])
app.include_router(proxily_router, dependencies=[auth_dependency])

# include lenco router for manual tests (or remove if you prefer)
app.include_router(lenco_router, dependencies=[auth_dependency])

# webhook router included without auth (Lenco will POST to this)
app.include_router(webhook_router)




# Ping endpoint
@app.get("/ping")
@limiter.limit("5/minute")
async def ping(request: Request):
    return {"message": "pong"}


# Premium expiry check endpoint (manual trigger)
@app.post("/payments/check-expiry")
async def run_premium_expiry_check():
    try:
        check_and_update_premium_expiry()
        return {"ok": True, "message": "Premium expiry check completed"}
    except Exception as e:
        logger.error(f"[EXPIRY CHECK] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Expiry check failed: {str(e)}")


# Startup scheduled job + bootstrap
@app.on_event("startup")
async def startup_event():
    key = ensure_initial_admin_api_key()
    if key:
        logger.info(f"[BOOTSTRAP] Created initial admin API key: {key}")

    scheduler = AsyncIOScheduler()

    # Existing premium expiry check
    scheduler.add_job(check_and_update_premium_expiry, "interval", days=1)

    # New: run event notifications daily at 07:00 for each university
    for uni in ["CUZ", "UNZA", "CBU"]:
     scheduler.add_job(
        lambda u=uni: asyncio.create_task(notify_upcoming_events(u)),
        "cron",
        hour=7,
    )


    scheduler.start()
    logger.info("[SCHEDULER] Premium expiry + event notifications scheduled daily.")



# ------------------------------
# Payment Test Model
# ------------------------------
from pydantic import BaseModel

class PaymentRequest(BaseModel):
    student_id: str
    university: str
    msisdn: str

@app.post("/payments/test")
async def test_payment(req: PaymentRequest):
    try:
        logger.debug(f"[PAYMENT TEST] student_id={req.student_id} university={req.university} msisdn={req.msisdn}")

        result = await process_payment(
            student_id=req.student_id,
            university=req.university,
            promo_code=None,
            override_msisdn=req.msisdn,
        )

        # Wrap orchestration result in Lenco-style schema
        return {
            "status": True if isinstance(result, dict) else False,
            "message": "Payment test processed",
            "data": [result] if isinstance(result, dict) else [],
            "meta": {
                "total": 1 if isinstance(result, dict) else 0,
                "pageCount": 1,
                "perPage": 1,
                "currentPage": 1
            }
        }

    except Exception as e:
        logger.error(f"[PAYMENT TEST] Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Payment failed: {str(e)}")


# ------------------------------
# Webhook (Lenco -> your app)
# ------------------------------
# NOTE: signature verification implemented. You asked to keep hard-coded info:
WEBHOOK_SIGNING_SECRET = "99137b878b12cd6e1a874f528ba48afc71b99077a4a763880ec536855fccec48"
# Lenco might send signature in different headers depending on config; check dashboard.
POSSIBLE_SIGNATURE_HEADERS = [
    "x-lenco-signature",
    "lenco-signature",
    "x-webhook-signature",
    "x-signature",
    "signature",
]


def _verify_webhook_signature(secret: str, body: bytes, header_value: str) -> bool:
    """
    Compute HMAC-SHA256(hex) of body using secret and compare to header_value.
    Supports header_value being raw hex or prefixed like 'sha256=...'.
    """
    if not header_value:
        return False

    # if header contains prefix like "sha256=..."
    if "=" in header_value and header_value.split("=", 1)[0].lower() in {"sha256", "sha1"}:
        _, header_value = header_value.split("=", 1)

    try:
        computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        # compare in constant time
        return hmac.compare_digest(computed, header_value)
    except Exception as e:
        logger.exception("[WEBHOOK] signature verification error: %s", e)
        return False


@webhook_router.post("/lenco")
async def lenco_webhook(request: Request):
    """
    Receives Lenco webhook POST requests.
    Verifies signature header (HMAC-SHA256) against the raw request body.
    If signature is valid, processes the payload (activates premium on SUCCESSFUL).
    """
    try:
        raw_body = await request.body()
        header_sig = None
        for hname in POSSIBLE_SIGNATURE_HEADERS:
            val = request.headers.get(hname)
            if val:
                header_sig = val
                break

        if not header_sig:
            logger.warning("[WEBHOOK] No signature header found. Rejecting.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature header")

        if not _verify_webhook_signature(WEBHOOK_SIGNING_SECRET, raw_body, header_sig):
            logger.warning("[WEBHOOK] Signature mismatch.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

        # parse JSON safely
        try:
            data = await request.json()
        except Exception:
            # fallback: try loading from raw bytes
            import json
            data = json.loads(raw_body.decode("utf-8"))

        transaction_id = data.get("id")
        status_val = data.get("status")
        metadata = data.get("metadata", {})

        student_id = metadata.get("student_id")
        university = metadata.get("university")

        if not student_id or not university:
            logger.error("[WEBHOOK] Missing student_id or university in metadata")
            return JSONResponse(status_code=400, content={"ok": False, "error": "Missing student_id or university"})

        logger.info(f"[WEBHOOK] student_id={student_id} university={university} status={status_val} transaction_id={transaction_id}")

        student = get_student_record(student_id, university) or {}
        if status_val and str(status_val).upper() == "SUCCESSFUL":
            now = datetime.utcnow()
            student["premium"] = True
            student["premiumActivatedAt"] = now.isoformat()
            student["premiumExpiresAt"] = (now + relativedelta(months=1)).isoformat()
            save_student_record(student_id, university, student)
            logger.info(f"[WEBHOOK] Premium activated for {student_id}@{university}")

        return {"ok": True, "transaction_id": transaction_id, "status": status_val}

    except HTTPException:
        # re-raise fastapi HTTP errors so they return correct status
        raise
    except Exception as e:
        logger.exception("[WEBHOOK] Unexpected error processing webhook: %s", e)
        # return 500 but do not crash the app
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")
    
# Messages router
messages_router = APIRouter(prefix="/messages", tags=["messages"])

@messages_router.get("/{university}/{student_id}")
async def get_student_messages(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Fetch personal messages for a student."""
    # Ownership check
    if current_user.get("user_id") != student_id or current_user.get("university") != university:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        # ✅ FIXED PATH: Collection -> Doc -> Collection -> Doc -> Collection
        coll_ref = (
            db.collection("MESSAGES")
            .document(university)
            .collection("students")  # Intermediate Collection
            .document(student_id)    # Student Document
            .collection("messages")  # Messages sub-collection
        )
        
        docs = list(coll_ref.stream())
        messages = []
        for doc in docs:
            data = doc.to_dict() or {}
            messages.append(
                {
                    "id": doc.id,
                    "title": data.get("title"),
                    "body": data.get("body"),
                    "timestamp": data.get("timestamp"),
                    "read": data.get("read", False),
                    "type": data.get("type", "system"),
                }
            )

        # Sort by timestamp descending
        messages.sort(key=lambda m: m.get("timestamp", "") or "", reverse=True)

        # Pagination logic
        start = (page - 1) * limit
        end = min(start + limit, len(messages))
        paginated = messages[start:end]

        return {
            "data": paginated,
            "total": len(messages),
            "total_pages": (len(messages) + limit - 1) // limit,
            "current_page": page,
        }

    except Exception as e:
        print(f"❌ get_student_messages error: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching messages: {str(e)}")


@messages_router.put("/{university}/{student_id}/{message_id}/read")
async def mark_message_read(
    university: str,
    student_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark a message as read for a student."""
    if current_user.get("user_id") != student_id or current_user.get("university") != university:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        # ✅ FIXED PATH: Must match the GET path exactly
        doc_ref = (
            db.collection("MESSAGES")
            .document(university)
            .collection("students")
            .document(student_id)
            .collection("messages")
            .document(message_id)
        )
        
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Message not found")

        doc_ref.set({"read": True}, merge=True)
        return {"ok": True, "message": "Message marked as read"}
        
    except Exception as e:
        print(f"❌ mark_message_read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Include messages router (protected)
app.include_router(messages_router, dependencies=[auth_dependency])

app = FastAPI() # Example route 
@app.get("/health") 
def health_check(): 
    return {"status": "ok"}
