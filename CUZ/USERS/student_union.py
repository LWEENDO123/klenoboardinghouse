# USERS/student_union.py
from fastapi import APIRouter, Depends, HTTPException
from payment.firestore_adapter import (
    get_union_member_by_code,
    db  # reuse Firestore client
)
from USERS.security import get_current_user  # your existing JWT decode
from Event.models import Event
from core.firebase import db as core_db
from core.config import CLUSTERS
from core.security import get_student_union_or_higher
from datetime import datetime
import random

# import notification sender
from firebase_admin import messaging
from google.cloud import firestore

router = APIRouter(prefix="/union", tags=["union"])

# ---------------------------
# Dependency: only union members can access
# ---------------------------
async def get_union_member(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "student_union":
        raise HTTPException(status_code=403, detail="Union member access required")
    return current_user



# ---------------------------
# Dependency: only union members can access
# ---------------------------
async def get_union_member(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "student_union":
        raise HTTPException(status_code=403, detail="Union member access required")
    return current_user

# ---------------------------
# Response model
# ---------------------------
class UnionProfile(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str
    referral_code: str

# ---------------------------
# Profile endpoint
# ---------------------------
@router.get("/profile", response_model=UnionProfile)
async def union_profile(current_user: dict = Depends(get_union_member)):
    university = current_user["university"]
    code = current_user["referral_code"]

    union_id, union_doc = get_union_member_by_code(university, code)
    if not union_doc:
        raise HTTPException(status_code=404, detail="Union member not found")

    return UnionProfile(
        first_name=union_doc.get("first_name", ""),
        last_name=union_doc.get("last_name", ""),
        email=union_doc.get("email", ""),
        phone=union_doc.get("phone", ""),
        referral_code=union_doc.get("referral_code", "")

# ---------------------------
# Simplified transactions endpoint
# ---------------------------
@router.get("/transactions/simple")
async def union_transactions_simple(current_user: dict = Depends(get_union_member)):
    """
    Return simplified transaction notifications for a union member.
    Only transactionId + message are exposed to the dashboard.
    """
    university = current_user["university"]
    code = current_user["referral_code"]

    union_id, union_doc = get_union_member_by_code(university, code)
    if not union_doc:
        raise HTTPException(status_code=404, detail="Union member not found")

    notif_ref = (
        db.collection("USERS")
        .document(university)
        .collection("studentunion")
        .document(union_id)
        .collection("notifications")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .stream()
    )

    notifications = [n.to_dict() for n in notif_ref]

    # Only return transactionId + message
    simplified = [
        {
            "transactionId": n.get("transactionId"),
            "message": n.get("message"),
            "timestamp": n.get("timestamp"),
        }
        for n in notifications
    ]

    return {"notifications": simplified}

# ---------------------------
# Payouts endpoint
# ---------------------------
@router.get("/payouts")
async def union_payouts(current_user: dict = Depends(get_union_member)):
    university = current_user["university"]
    code = current_user["referral_code"]

    union_id, union_doc = get_union_member_by_code(university, code)
    if not union_doc:
        raise HTTPException(status_code=404, detail="Union member not found")

    return {"payouts": union_doc.get("payouts", [])}
# ---------------------------
# Referrals endpoint (awareness messages with transaction IDs)
# ---------------------------
@router.get("/referrals")
async def union_referrals(current_user: dict = Depends(get_union_member)):
    code = current_user["referral_code"]

    doc = db.collection("referral_codes").document(code).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Referral code not found")

    data = doc.to_dict()
    usages = data.get("usages", [])

    # Build awareness messages only from successful transactions
    messages = []
    for u in usages:
        txn_id = u.get("payoutId") or u.get("transactionId") or "unknown"
        status = (u.get("payoutStatus") or "").upper()
        if status in {"SUCCESSFUL", "COMPLETED", "SUCCESS", "PAID"}:
            # Make it sound more like a notification
            messages.append(
                f"🎉 Great news! Your referral code '{code}' was successfully used. "
                f"Transaction ID: {txn_id}"
            )

    return {
        "code": code,
        "successfulUses": len(messages),
        "awarenessMessages": messages
    }


# ---------------------------
# Event creation endpoint (posts both scoped and global + sends notification)
# ---------------------------
@router.post("/{university}/create_event_both")
async def create_union_event_both(university: str, event: Event, current_user: dict = Depends(get_student_union_or_higher)):
    """
    Allow union members to create events.
    Posts both scoped (university only) and global (cluster-wide).
    Also sends a notification to students in the university.
    """
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    # enforce event_type = university
    event_data = event.dict()
    event_data["event_type"] = "university"
    event_data["created_by"] = current_user["user_id"]

    # generate event_id
    event_id = f"{event.title[0].upper()}{datetime.now().strftime('%m%d%Y')}{random.randint(100000,999999)}"

    # Step 1: Scoped (university only)
    core_db.collection("EVENT").document(university).collection("events").document(event_id).set(event_data)

    # Step 2: Global (cluster-wide)
    if university in CLUSTERS:
        cluster_unis = CLUSTERS[university]
        for uni in cluster_unis:
            core_db.collection("EVENT").document(uni).collection("events").document(event_id).set(event_data)

    # Step 3: Send notification
    try:
        payload = {
            "event_id": event_id,
            "detail_url": "",
            "image_url": event.image_url or "",
            "video_url": event.video_url or ""
        }
        message = messaging.Message(
            notification=messaging.Notification(
                title=f"New Event: {event.title}",
                body=f"{event.title} scheduled on {event.date} at {event.time}"
            ),
            topic=f"university_{university}",
            data={k: str(v) for k, v in payload.items()}
        )
        fcm_response = messaging.send(message)

        # Store notification in Firestore
        notif_data = {
            "title": f"New Event: {event.title}",
            "body": f"{event.title} scheduled on {event.date} at {event.time}",
            "category": "university",
            "event_id": event_id,
            "image_url": event.image_url,
            "video_url": event.video_url,
            "timestamp": datetime.utcnow(),
            "read_by": []
        }
        core_db.collection("USERS").document(university).collection("notifications").add(notif_data)
    except Exception as e:
        # log but don’t block event creation if notification fails
        print(f"Notification error: {e}")
        fcm_response = None

    return {
        "message": "✅ Event created in both scoped and global collections, notification sent",
        "event_id": event_id,
        "data": event_data,
        "cluster": CLUSTERS.get(university, [university]),
        "fcm_response": fcm_response
    }




# ---------------------------
# Dependency: only union members can access
# ---------------------------
async def get_union_member(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "student_union":
        raise HTTPException(status_code=403, detail="Union member access required")
    return current_user

@router.get("/dashboard")
async def union_dashboard(current_user: dict = Depends(get_union_member)):
    """
    Return summary stats for the union member dashboard.
    Includes total number of payouts.
    """
    university = current_user["university"]
    code = current_user["referral_code"]

    union_id, union_doc = get_union_member_by_code(university, code)
    if not union_doc:
        raise HTTPException(status_code=404, detail="Union member not found")

    payouts = union_doc.get("payouts", [])
    total_payouts = len(payouts)

    return {
        "total_payouts": total_payouts,
        "payouts": payouts  # optional: include full list if needed
    }





@router.post("/{university}/students/{student_id}/upload_event_image")
async def upload_event_image(university: str, student_id: str, file: UploadFile = File(...)) -> Dict[str, str]:
    """
    Upload and compress a single event image (PNG/JPG).
    - Resizes to 1280x720 max
    - Stores in Firebase Storage
    - Returns signed URL
    """
    try:
        # Validate file type
        if not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image files are allowed (PNG/JPG).")

        # Read file bytes
        file_bytes = await file.read()

        # Compress to 1280x720
        compressed_bytes = compress_to_720(file_bytes)

        # Upload to Firebase
        signed_url = upload_to_firebase(
            university=university,
            student_id=student_id,
            file_bytes=compressed_bytes,
            filename=file.filename or "event.jpg",
            expiry_hours=24
        )

        return {"status": "success", "url": signed_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")
