# file: CUZ/main.py

# Standard library
# Standard library
import os
import json
import logging
import asyncio
import urllib.parse
import hmac
import hashlib
from datetime import datetime
from fastapi.staticfiles import StaticFiles
# FastAPI core + responses
from fastapi import FastAPI, Depends, Request, APIRouter, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, Response, FileResponse


# Third‑party
from dateutil.relativedelta import relativedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel
from botocore.exceptions import ClientError
from CUZ.yearbook.profile.storage import s3_client, RAILWAY_BUCKET

# ------------------------------
# Routers and auth
# ------------------------------
from CUZ.yearbook.profile.events import router as event_router
from fastapi.staticfiles import StaticFiles
from CUZ.Notification.notification import router as notification_router, notify_upcoming_events
from CUZ.USERS.user_routes import router as user_router
from CUZ.Available.checkboarding import router as available_router
from CUZ.PINNED.pinned import router as pinned_router
from CUZ.PINNED import user_routes as pinned_user_routes
from CUZ.HOME.add_boardinghouse import router as boardinghouse_router
from CUZ.HOME.user_routes import router as user_home_router
from CUZ.Store.store import router as store_router
from CUZ.ProxyLocation.fine_me import router as proxily_router
from CUZ.core.security import get_current_user
from CUZ.yearbook.profile.video import router as video_router

# Payment modules
from CUZ.payment.firestore_adapter import get_student_record, save_student_record
from CUZ.payment.lenco_gateway import router as lenco_router
from CUZ.payment.payment_orchestrator import (
    check_and_update_premium_expiry,
    process_payout,
)


# Firebase bootstrap (Railway)
logger = logging.getLogger("firebase.bootstrap")
CREDS_JSON_ENV = "GOOGLE_APPLICATION_CREDENTIALS_JSON"
CREDS_PATH = "/app/firebase.json"

if CREDS_JSON_ENV in os.environ and not os.path.exists(CREDS_PATH):
    try:
        creds = json.loads(os.environ[CREDS_JSON_ENV])
        with open(CREDS_PATH, "w") as f:
            json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDS_PATH
        logger.info("🔥 Firebase credentials written to %s", CREDS_PATH)
    except Exception as e:
        logger.exception("❌ Failed to write Firebase credentials: %s", e)
        raise

from CUZ.core.firebase import db
import CUZ.core.security

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# App initialization
app = FastAPI(title="Baodinghouse API")

# Routers
debug_router = APIRouter(prefix="/debug", tags=["debug"])
webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])

# Messages router must be defined BEFORE inclusion
messages_router = APIRouter(prefix="/messages", tags=["messages"])

@messages_router.get("/{university}/{student_id}")
async def get_student_messages(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    # Ownership check
    if current_user.get("user_id") != student_id or current_user.get("university") != university:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        coll_ref = (
            db.collection("MESSAGES")
            .document(university)
            .collection("students")
            .document(student_id)
            .collection("messages")
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
        logger.exception("❌ get_student_messages error: %s", e)
        raise HTTPException(status_code=500, detail=f"Error fetching messages: {str(e)}")


@messages_router.put("/{university}/{student_id}/{message_id}/read")
async def mark_message_read(
    university: str,
    student_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("user_id") != student_id or current_user.get("university") != university:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
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
        logger.exception("❌ mark_message_read error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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


import os

# ------------------------------
# Webhook (Lenco -> your app)
# ------------------------------

# Load secret from Railway environment variable
WEBHOOK_SIGNING_SECRET = os.getenv(
    "WEBHOOK_SIGNING_SECRET",
    "dev-fallback-secret"  # optional fallback for local testing
)

POSSIBLE_SIGNATURE_HEADERS = [
    "x-lenco-signature",
    "lenco-signature",
    "x-webhook-signature",
    "x-signature",
    "signature",
]

def _verify_webhook_signature(secret: str, body: bytes, header_value: str) -> bool:
    if not header_value:
        return False
    if "=" in header_value and header_value.split("=", 1)[0].lower() in {"sha256", "sha1"}:
        _, header_value = header_value.split("=", 1)
    try:
        computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(computed, header_value)
    except Exception as e:
        logger.exception("[WEBHOOK] signature verification error: %s", e)
        return False

@webhook_router.post("/lenco")
async def lenco_webhook(request: Request):
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

        try:
            data = await request.json()
        except Exception:
            import json as _json
            data = _json.loads(raw_body.decode("utf-8"))

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
        raise
    except Exception as e:
        logger.exception("[WEBHOOK] Unexpected error processing webhook: %s", e)
        raise HTTPException(status_code=500, detail=f"Webhook processing error: {str(e)}")








# Always available (no auth required)
app.include_router(debug_router)
app.include_router(user_router)        # login/signup open
app.include_router(webhook_router)     # webhook open

# Protected routers (require JWT Bearer token)
app.include_router(messages_router, dependencies=[Depends(get_current_user)])
app.include_router(user_home_router, dependencies=[Depends(get_current_user)])
app.include_router(pinned_router, dependencies=[Depends(get_current_user)])
app.include_router(pinned_user_routes.router, dependencies=[Depends(get_current_user)])
app.include_router(available_router, dependencies=[Depends(get_current_user)])
app.include_router(event_router, dependencies=[Depends(get_current_user)])
app.include_router(notification_router, dependencies=[Depends(get_current_user)])
app.include_router(boardinghouse_router, dependencies=[Depends(get_current_user)])
app.include_router(store_router, dependencies=[Depends(get_current_user)])
app.include_router(proxily_router, dependencies=[Depends(get_current_user)])
app.include_router(lenco_router, dependencies=[Depends(get_current_user)])
app.include_router(video_router)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "IOS.web"), html=True),
    name="static"
)

app.mount(
    "/",
    StaticFiles(directory=os.path.join(BASE_DIR, "IOS.web"), html=True),
    name="root"
)

@app.get("/index")
async def serve_index():
    index_path = os.path.join(BASE_DIR, "IOS.web", "index.html")
    return FileResponse(index_path, media_type="text/html")







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

# Startup scheduled job
@app.on_event("startup")
async def startup_event():
    """
    Scheduler starts on app startup. If you want to seed CONFIG/jwt or other
    Firestore documents, do it here (synchronously or via asyncio.to_thread).
    """
    scheduler = AsyncIOScheduler()

    # Existing premium expiry check
    scheduler.add_job(check_and_update_premium_expiry, "interval", days=1)

    # Run event notifications daily at 07:00 for each university
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
# Messages endpoints (already protected via router dependency)
# ------------------------------
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
        coll_ref = (
            db.collection("MESSAGES")
            .document(university)
            .collection("students")
            .document(student_id)
            .collection("messages")
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
        logger.exception("❌ get_student_messages error: %s", e)
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
        logger.exception("❌ mark_message_read error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------
# Payment Test Model + endpoint
# ------------------------------
class PaymentRequest(BaseModel):
    student_id: str
    university: str
    msisdn: str

@app.post("/payments/test")
async def test_payment(req: PaymentRequest):
    try:
        logger.debug(f"[PAYMENT TEST] student_id={req.student_id} university={req.university} msisdn={req.msisdn}")

        result = await process_payout(
            student_id=req.student_id,
            university=req.university,
            msisdn=req.msisdn,
        )

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
        logger.exception("[PAYMENT TEST] Error: %s", e)
        raise HTTPException(status_code=500, detail=f"Payment failed: {str(e)}")


# ------------------------------
# Optional: health endpoint for Firebase
# ------------------------------
@app.get("/firebase/health")
async def firebase_health():
    try:
        # quick checks that db and storage are accessible
        project = getattr(db, "project", None)
        return {"ok": True, "firestore_project": project}
    except Exception as e:
        logger.exception("Firebase health check failed: %s", e)
        raise HTTPException(status_code=500, detail="Firebase health check failed")


# ------------------------------
# Device Registration Endpoint (updated)
# ------------------------------
from pydantic import BaseModel

class DeviceRegisterRequest(BaseModel):
    university: str
    user_id: str          # student_id or landlord_id
    role: str             # "student", "landlord", or "admin"
    device_token: str     # FCM token or unique device ID
    platform: str = "android"  # optional: android/ios/web

@app.post("/device/register")
async def register_device(
    req: DeviceRegisterRequest,
    current_user: dict = Depends(get_current_user),
):
    logger.info(
        "📱 Device register attempt → user_id=%s university=%s role=%s platform=%s",
        req.user_id, req.university, req.role, req.platform
    )

    # Ownership check
    if current_user:
        logger.debug("Current user context: %s", current_user)
        if (
            current_user.get("user_id") != req.user_id
            or current_user.get("university") != req.university
        ):
            logger.warning("Unauthorized device registration attempt")
            raise HTTPException(status_code=403, detail="Not authorized")

    try:
        doc_ref = db.collection("DEVICES").document(req.user_id)
        existing_doc = doc_ref.get()
        existing = existing_doc.to_dict() if existing_doc.exists else None

        logger.debug("Existing device record: %s", existing)

        # Invalidate old device
        if existing and existing.get("device_token") != req.device_token:
            doc_ref.update({
                "active": False,
                "invalidated_at": datetime.utcnow().isoformat()
            })
            logger.info("🔄 Old device invalidated for user=%s", req.user_id)

        # Save new device
        doc_ref.set({
            "university": req.university,
            "user_id": req.user_id,
            "role": req.role,
            "device_token": req.device_token,
            "platform": req.platform,
            "registered_at": datetime.utcnow().isoformat(),
            "active": True,
        }, merge=True)

        logger.info("✅ Device registered successfully for user=%s", req.user_id)

        return {
            "ok": True,
            "message": f"Device registered for {req.role}",
        }

    except Exception as e:
        logger.exception("❌ Device registration error")
        raise HTTPException(status_code=500, detail="Error registering device")






class FCMRegistration(BaseModel):
    student_id: str
    university: str
    fcm_token: str

@app.post("/users/register_fcm")
async def register_fcm(
    req: FCMRegistration,
    current_user: dict = Depends(get_current_user),
):
    logger.info(
        "🔔 FCM registration attempt → student_id=%s university=%s",
        req.student_id, req.university
    )

    if (
        current_user.get("user_id") != req.student_id
        or current_user.get("university") != req.university
    ):
        logger.warning("Unauthorized FCM registration")
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        ref = (
            db.collection("USERS")
            .document(req.university)
            .collection("students")
            .document(req.student_id)
        )

        ref.set({
            "fcm_token": req.fcm_token,
            "updated_at": datetime.utcnow().isoformat(),
        }, merge=True)

        logger.info("✅ FCM token saved for user=%s", req.student_id)

        return {"ok": True, "message": "FCM token registered"}

    except Exception:
        logger.exception("❌ FCM registration error")
        raise HTTPException(status_code=500, detail="Error registering FCM token")






logger = logging.getLogger("media_proxy")

@app.get("/media/{file_path:path}")
async def get_media_proxy(file_path: str, request: Request):
    """
    Proxy endpoint for serving media (images/videos) from S3.
    Supports Range requests for efficient video streaming.
    """
    try:
        # 1. Fetch object metadata
        head = s3_client.head_object(Bucket=RAILWAY_BUCKET, Key=file_path)
        file_size = head["ContentLength"]
        content_type = head.get("ContentType", "application/octet-stream")

        # 2. Check for Range header
        range_header = request.headers.get("range")
        if range_header:
            try:
                # Parse Range header: e.g. "bytes=0-1023"
                range_value = range_header.strip().lower().replace("bytes=", "")
                start_str, end_str = range_value.split("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1

                # Clamp values
                if start < 0:
                    start = 0
                if end >= file_size:
                    end = file_size - 1

                length = end - start + 1

                # Fetch partial content from S3
                obj = s3_client.get_object(
                    Bucket=RAILWAY_BUCKET,
                    Key=file_path,
                    Range=f"bytes={start}-{end}"
                )

                return Response(
                    content=obj["Body"].read(),
                    status_code=206,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(length),
                        "Content-Type": content_type,
                    },
                )
            except Exception as e:
                logger.error(f"Range request parsing failed: {e}")
                raise HTTPException(status_code=400, detail="Invalid Range header")

        # 3. No Range header → stream whole file
        obj = s3_client.get_object(Bucket=RAILWAY_BUCKET, Key=file_path)
        return StreamingResponse(
            obj["Body"],
            media_type=content_type,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=31536000",
                "X-Content-Type-Options": "nosniff",
            },
        )

    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail=f"File not found")
    except Exception as e:
        logger.error(f"Proxy streaming error for {file_path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching file")





