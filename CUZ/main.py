# file: CUZ/main.py

from fastapi import FastAPI, Depends, Request, APIRouter, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import os
import json
import logging
import hmac
import hashlib
from datetime import datetime
from dateutil.relativedelta import relativedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel
from CUZ.yearbook.profile.storage import upload_file_bytes, s3_client, RAILWAY_BUCKET
from fastapi.responses import StreamingResponse
from CUZ.yearbook.profile.storage import s3_client, RAILWAY_BUCKET




# ------------------------------
# Routers and auth
# ------------------------------
from CUZ.yearbook.profile.events import router as event_router
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
# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from CUZ.core.firebase import db
import CUZ.core.security



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




# App initialization
app = FastAPI(title="Baodinghouse API")

# Routers
debug_router = APIRouter(prefix="/debug", tags=["debug"])


# Messages router must be defined BEFORE inclusion
messages_router = APIRouter(prefix="/messages", tags=["messages"])

# ==============================
# Messages Router Endpoints
# ==============================

@messages_router.get("/{university}/{student_id}")
async def get_student_messages(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """
    Fetch paginated messages for a student (latest first).
    """
    # Ownership check
    if (
        current_user.get("user_id") != student_id
        or current_user.get("university") != university
    ):
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
        messages = [
            {
                "id": doc.id,
                "title": (doc.to_dict() or {}).get("title"),
                "body": (doc.to_dict() or {}).get("body"),
                "timestamp": (doc.to_dict() or {}).get("timestamp"),
                "read": (doc.to_dict() or {}).get("read", False),
                "type": (doc.to_dict() or {}).get("type", "system"),
            }
            for doc in docs
        ]

        # newest first
        messages.sort(
            key=lambda m: m.get("timestamp") or "",
            reverse=True,
        )

        start = (page - 1) * limit
        end = start + limit

        return {
            "data": messages[start:end],
            "total": len(messages),
            "total_pages": (len(messages) + limit - 1) // limit,
            "current_page": page,
        }

    except Exception as e:
        logger.exception("❌ get_student_messages failed")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching messages: {str(e)}",
        )


@messages_router.put("/{university}/{student_id}/{message_id}/read")
async def mark_message_read(
    university: str,
    student_id: str,
    message_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Mark a specific message as read.
    """
    if (
        current_user.get("user_id") != student_id
        or current_user.get("university") != university
    ):
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

        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Message not found")

        doc_ref.set({"read": True}, merge=True)
        return {"ok": True}

    except Exception as e:
        logger.exception("❌ mark_message_read failed")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================
# Logging
# ==============================

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


# ==============================
# Debug Router
# ==============================

@debug_router.post("/headers")
async def debug_headers(request: Request):
    return {
        "authorization": request.headers.get("authorization"),
        "x_api_key": request.headers.get("x-api-key"),
        "host": request.headers.get("host"),
    }


# ==============================
# Middleware
# ==============================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["1000/hour"])
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests",
            "retry_after_seconds": exc.reset_in,
        },
    )
    response.headers["Retry-After"] = str(exc.reset_in)
    return response


# ==============================
# Webhook Router
# ==============================

webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])


# ==============================
# Router Registration
# ==============================

# Public
app.include_router(debug_router)
app.include_router(user_router)
app.include_router(webhook_router)

# Protected
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


# ==============================
# Health / Ping
# ==============================

@app.get("/ping")
@limiter.limit("5/minute")
async def ping(request: Request):
    return {"message": "pong"}


# ==============================
# Payment Test Endpoint
# ==============================

class PaymentRequest(BaseModel):
    student_id: str
    university: str
    msisdn: str


@app.post("/payments/test")
async def test_payment(req: PaymentRequest):
    try:
        logger.debug(
            "[PAYMENT TEST] student=%s university=%s",
            req.student_id,
            req.university,
        )

        result = await process_payout(
            student_id=req.student_id,
            university=req.university,
            msisdn=req.msisdn,
        )

        return {
            "status": isinstance(result, dict),
            "message": "Payment test processed",
            "data": [result] if isinstance(result, dict) else [],
        }

    except Exception as e:
        logger.exception("[PAYMENT TEST] failed")
        raise HTTPException(
            status_code=500,
            detail=f"Payment failed: {str(e)}",
        )


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
# Device Registration Endpoint
# ------------------------------
from pydantic import BaseModel

class DeviceRegisterRequest(BaseModel):
    university: str
    user_id: str          # can be student_id or landlord_id
    role: str             # "student", "landlord", or "admin"
    device_token: str     # FCM token or unique device ID
    platform: str = "android"  # optional: android/ios/web

@app.post("/device/register")
async def register_device(
    req: DeviceRegisterRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Register a device for notifications / tracking.
    - Students: must match their own student_id + university
    - Landlords/Admins: must match their own user_id + role
    Stores under DEVICES/{user_id} with metadata.
    """
    # ✅ Ownership / role check
    if current_user.get("role") == "student":
        if current_user.get("user_id") != req.user_id or current_user.get("university") != req.university:
            raise HTTPException(status_code=403, detail="Not authorized as student")
    elif current_user.get("role") in ["landlord", "admin"]:
        if current_user.get("user_id") != req.user_id or current_user.get("role") != req.role:
            raise HTTPException(status_code=403, detail="Not authorized as landlord/admin")
    else:
        raise HTTPException(status_code=403, detail="Unsupported role")

    try:
        doc_ref = db.collection("DEVICES").document(req.user_id)
        doc_ref.set({
            "university": req.university,
            "user_id": req.user_id,
            "role": req.role,
            "device_token": req.device_token,
            "platform": req.platform,
            "registered_at": datetime.utcnow().isoformat(),
        }, merge=True)

        return {"ok": True, "message": f"Device registered for {req.role}"}
    except Exception as e:
        logger.exception("❌ Device registration error: %s", e)
        raise HTTPException(status_code=500, detail=f"Error registering device: {str(e)}")



# This endpoint catches any URL starting with /media/ and fetches it from S3
@app.get("/media/{file_path:path}")
async def get_media_proxy(file_path: str):
    """
    Streams the image with correct headers to prevent forced downloads.
    """
    try:
        # 1. Fetch from S3
        obj = s3_client.get_object(Bucket=RAILWAY_BUCKET, Key=file_path)
        
        # 2. Get the specific content type (e.g., image/jpeg, image/png)
        content_type = obj.get('ContentType', 'image/jpeg')

        # 3. Stream with headers that force 'inline' display
        return StreamingResponse(
            obj['Body'], 
            media_type=content_type,
            headers={
                # 'inline' tells the browser: "Show this on the screen"
                "Content-Disposition": f"inline; filename={file_path.split('/')[-1]}",
                # Cache for 1 year to make the yearbook feel snappy
                "Cache-Control": "public, max-age=31536000",
                # Prevents browsers from trying to guess a different MIME type
                "X-Content-Type-Options": "nosniff"
            }
        )
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="Image not found")
    except Exception as e:
        logger.error(f"Proxy streaming error: {e}")
        raise HTTPException(status_code=500, detail="Error fetching image")



