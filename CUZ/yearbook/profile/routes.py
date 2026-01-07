#Yearbook/profile/routes.py
import logging
logger = logging.getLogger("yearbook")
logger.setLevel(logging.DEBUG)
from routers.region_router import recalculate_origin


# ---------------------------
# Standard Library
# ---------------------------
from datetime import datetime
from typing import List, Optional

# ---------------------------
# FastAPI & Pydantic
# ---------------------------
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from pydantic import BaseModel, EmailStr, constr

# ---------------------------
# Core Modules
# ---------------------------
from core.firebase import db, firestore
from core.security import (
    get_current_user,
    get_current_admin,
    get_student_or_admin,
)

# ---------------------------
# Local Modules
# ---------------------------
from .models import (
    Userprofile,
    FinalSemesterEntry,
    QAItem,
    HomepageCard,
    StudentDetailView,
    EventCard,
)
from .compress import compress_to_720
from .security import validate_image
from .storage import upload_compressed_image
from .identity import assert_student_exists, assert_owns_resource_or_admin
from .events import assert_event_portal_open, today_event_id


router = APIRouter(prefix="/yearbook/profile", tags=["Yearbook Profile"])


# ---------------------------
# EVENT UPLOAD
# ---------------------------

@router.post("/{university}/{student_id}/events/photos")
async def upload_event_photos(
    university: str,
    student_id: str,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_student_or_admin),
):
    """
    Upload photos automatically linked to today's official event for the student's university.
    """
    assert_owns_resource_or_admin(current_user, university, student_id)
    await assert_student_exists(university, student_id)

    # ✅ Automatically resolve today's event ID for this university
    event_id = today_event_id()   # helper that generates/returns today's event identifier
    assert_event_portal_open(university, event_id)

    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Max 10 photos allowed per event")

    photo_urls = []
    for file in files:
        raw = await file.read()
        validate_image(raw, file.filename)
        compressed = compress_to_720(raw)
        url = upload_compressed_image(university, student_id, compressed, file.filename, public=False)
        photo_urls.append(url)

    now = datetime.utcnow().isoformat()

    # Save under student's yearbook profile, linked to today's event
    events_ref = (
        db.collection("yearbook")
          .document(university)
          .collection(student_id)
          .collection("events")
          .document(event_id)
    )
    events_ref.set({
        "photo_urls": photo_urls,
        "uploaded_at": now,
        "linked_event_id": event_id
    }, merge=True)

    return {
        "student_id": student_id,
        "event_id": event_id,
        "photo_urls": photo_urls,
        "university": university
    }




# ---------------------------
# FINAL SEMESTER UPLOAD
# ---------------------------
@router.post("/{university}/{student_id}/final")
async def upload_final_semester(
    university: str,
    student_id: str,
    file: UploadFile = File(...),
    caption: str = "",
    character: List[QAItem] = [],
    current_user: dict = Depends(get_student_or_admin),
):
    assert_owns_resource_or_admin(current_user, university, student_id)
    student_doc = await assert_student_exists(university, student_id)
    name = f"{student_doc.get('first_name', '')} {student_doc.get('last_name', '')}".strip()
    programme = student_doc.get("programme", "Unknown")
    semester_intake = student_doc.get("semester_intake", "Unknown")

    raw = await file.read()
    validate_image(raw, file.filename)
    compressed = compress_to_720(raw)
    url = upload_compressed_image(university, student_id, compressed, file.filename, public=False)

    final_entry = FinalSemesterEntry(
        id=f"final_{semester_intake}",
        name=name,
        programme=programme,
        semester_intake=semester_intake,
        character=character,
        caption=caption,
        photo_url=url
    )

    now = datetime.utcnow().isoformat()

    profile_ref = (
        db.collection("yearbook")
          .document(university)
          .collection(student_id)
          .document("profile")
    )
    profile_ref.set({
        **final_entry.dict(),
        "id": student_id,
        "last_updated": now
    }, merge=True)

    return final_entry.dict()


# ---------------------------
# HOMEPAGE FEED (GLOBAL)
# ---------------------------
@router.get("/feed/homepage_extended")
async def get_homepage_feed_extended(limit: int = 20):
    """
    Global feed combining official events with student uploads grouped by event_id.
    Each event category contains only the event title + student cards.
    """
    results = []

    # Loop through all universities' official events
    event_unis = db.collection("EVENT").stream()
    for uni_doc in event_unis:
        uni_id = uni_doc.id
        events = db.collection("EVENT").document(uni_id).collection("events").stream()
        for event_doc in events:
            event_data = event_doc.to_dict()
            event_id = event_doc.id

            # Collect student uploads tied to this event_id
            student_cards = []
            students_ref = db.collection("yearbook").document(uni_id).collections()
            for student_coll in students_ref:
                event_ref = (
                    db.collection("yearbook")
                      .document(uni_id)
                      .collection(student_coll.id)
                      .collection("events")
                      .document(event_id)
                )
                if event_ref.get().exists:
                    data = event_ref.get().to_dict()
                    photo_urls = data.get("photo_urls", [])
                    likes = data.get("likes", [])
                    if photo_urls:
                        student_cards.append({
                            "student_id": student_coll.id,
                            "photo_urls": photo_urls,
                            "likes_count": len(likes),
                            "uploaded_at": data.get("uploaded_at", "")
                        })

            # Build event group (only title shown as metadata)
            results.append({
                "event_id": event_id,
                "title": event_data.get("title"),  # used as subcategory name
                "students": student_cards,
                "last_updated": event_data.get("date")
            })

    # Sort event groups by date
    results.sort(key=lambda x: x["last_updated"], reverse=True)
    return {"items": results[:limit]}




# ---------------------------
# STUDENT DETAIL VIEW
# ---------------------------
@router.get("/feed/student/{university}/{student_id}", response_model=StudentDetailView)
async def get_student_detail(university: str, student_id: str):
    """
    Returns a student's detail view: profile info, events (latest → oldest), and final semester entry.
    """
    student_doc = await assert_student_exists(university, student_id)
    name = f"{student_doc.get('first_name', '')} {student_doc.get('last_name', '')}".strip()
    programme = student_doc.get("programme", "Unknown")
    semester_intake = student_doc.get("semester_intake", "Unknown")

    events_ref = (
        db.collection("yearbook")
          .document(university)
          .collection(student_id)
          .collection("events")
    )
    events = []
    for doc in events_ref.stream():
        data = doc.to_dict()
        events.append(EventCard(
            event_id=doc.id,
            photo_urls=data.get("photo_urls", []),
            uploaded_at=data.get("uploaded_at", "")
        ))
    events.sort(key=lambda e: e.uploaded_at, reverse=True)

    profile_ref = (
        db.collection("yearbook")
          .document(university)
          .collection(student_id)
          .document("profile")
    )
    profile_doc = profile_ref.get()
    final_semester = None
    if profile_doc.exists:
        data = profile_doc.to_dict()
        if "final_semester" in data:
            final_semester = FinalSemesterEntry(**data["final_semester"])

    return StudentDetailView(
        student_id=student_id,
        name=name,
        programme=programme,
        semester_intake=semester_intake,
        events=events,
        final_semester=final_semester
    )


# ---------------------------
# UNIVERSITY-SCOPED FEED
# ---------------------------@router.get("/feed/university/{university_id}")
async def get_university_feed(university_id: str, limit: int = 20):
    """
    University-scoped feed.
    Groups student uploads under each event_id for this university.
    Only event title is shown as metadata.
    """
    results = []

    events = db.collection("EVENT").document(university_id).collection("events").stream()
    for event_doc in events:
        event_data = event_doc.to_dict()
        event_id = event_doc.id

        student_cards = []
        students_ref = db.collection("yearbook").document(university_id).collections()
        for student_coll in students_ref:
            event_ref = (
                db.collection("yearbook")
                  .document(university_id)
                  .collection(student_coll.id)
                  .collection("events")
                  .document(event_id)
            )
            if event_ref.get().exists:
                data = event_ref.get().to_dict()
                photo_urls = data.get("photo_urls", [])
                likes = data.get("likes", [])
                if photo_urls:
                    student_cards.append({
                        "student_id": student_coll.id,
                        "photo_urls": photo_urls,
                        "likes_count": len(likes),
                        "uploaded_at": data.get("uploaded_at", "")
                    })

        results.append({
            "event_id": event_id,
            "title": event_data.get("title"),  # only title shown
            "students": student_cards,
            "last_updated": event_data.get("date")
        })

    results.sort(key=lambda x: x["last_updated"], reverse=True)
    return {"items": results[:limit]}




@router.post("/{university}/{student_id}/{event_id}/like")
async def toggle_like_event(
    university: str,
    student_id: str,
    event_id: str,
    current_user: dict = Depends(get_student_or_admin)
):
    """
    Toggle like/unlike for a student's event post.
    Each user can like once and unlike once.
    """
    viewer_id = current_user.get("user_id")
    viewer_uni = current_user.get("university")

    if not viewer_id or not viewer_uni:
        raise HTTPException(status_code=403, detail="Missing viewer identity")

    event_ref = (
        db.collection("yearbook")
          .document(university)
          .collection(student_id)
          .collection("events")
          .document(event_id)
    )
    event_doc = event_ref.get()
    if not event_doc.exists:
        raise HTTPException(status_code=404, detail="Event not found")

    data = event_doc.to_dict()
    likes = set(data.get("likes", []))

    if viewer_id in likes:
        likes.remove(viewer_id)
        action = "unliked"
    else:
        likes.add(viewer_id)
        action = "liked"

    event_ref.update({"likes": list(likes)})

    return {
        "message": f"Event {action} successfully",
        "likes_count": len(likes),
        "liked": viewer_id in likes
    }
   

@router.put("/{university}/{student_id}/premium/upgrade")
async def upgrade_to_premium(university: str, student_id: str, months: int = 1):
    """
    Check if a student has been upgraded to premium (via payment gateway).
    If premium is active and no message has been logged yet, create a message in
    MESSAGES/{university}/{student_id}/messages.
    """
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()

    now = datetime.utcnow()

    # Detect premium status (set by webhook or background job)
    premium_active = bool(data.get("premium")) or bool(data.get("premium_expires"))
    premium_expires = data.get("premium_expires")

    if not premium_active:
        return {
            "student_id": student_id,
            "university": university,
            "full_name": full_name,
            "premium": False,
            "message": "Student is not premium."
        }

    # Check if we already logged a message for this activation
    last_message_flag = data.get("last_premium_message_at")
    if last_message_flag and now.isoformat() <= last_message_flag:
        return {
            "student_id": student_id,
            "university": university,
            "full_name": full_name,
            "premium": True,
            "premium_expires": premium_expires,
            "message": "Premium already active, message previously logged."
        }

    # Log success message to MESSAGES/{university}/{student_id}/messages
    message_doc = {
        "title": "Premium Activated",
        "body": f"Your premium subscription is active until {premium_expires}.",
        "timestamp": now.isoformat(),
        "read": False,
        "type": "payment"
    }
    db.collection("MESSAGES").document(university).collection(student_id).collection("messages").add(message_doc)

    # Mark that we logged a message
    doc_ref.set({"last_premium_message_at": now.isoformat()}, merge=True)

    return {
        "student_id": student_id,
        "university": university,
        "full_name": full_name,
        "premium": True,
        "premium_expires": premium_expires,
        "message": f"Premium subscription for {full_name} ({student_id}) at {university} is active until {premium_expires}."
    }





@router.post("/users/{student_id}/programme")
async def set_programme(student_id: str, university: str, programme: str):
    student_doc = await assert_student_exists(university, student_id)
    db.collection("USERS").document(student_id).set(
        {"programme": programme}, merge=True
    )
    return {"student_id": student_id, "programme": programme}

@router.get("/users/{student_id}/programme")
async def get_programme(student_id: str, university: str):
    student_doc = await assert_student_exists(university, student_id)
    return {"student_id": student_id, "programme": student_doc.get("programme", "Unknown")}


@router.post("/users/{student_id}/premium")
async def set_premium(student_id: str, university: str, expires_at: str):
    db.collection("USERS").document(student_id).set(
        {"premium_expires": expires_at}, merge=True
    )
    return {"student_id": student_id, "premium_expires": expires_at}

@router.get("/users/{student_id}/premium")
async def get_premium(student_id: str, university: str):
    student_doc = await assert_student_exists(university, student_id)
    return {
        "student_id": student_id,
        "premium_expires": student_doc.get("premium_expires", None),
        "active": bool(student_doc.get("premium_expires"))
    }

@router.get("/{university}/{student_id}/profile", response_model=UserProfile)
async def get_user_profile(university: str, student_id: str, current_user: dict = Depends(get_current_user)):
    """
    Return basic profile info for a student, including full name and premium/free tier status.
    """
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()

    premium_active = bool(data.get("premium_expires")) or data.get("premium", False)

    return UserProfile(
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        email=data.get("email", ""),
        phone_number=data.get("phone_number", ""),
        university=university,
        premium=premium_active
    )






class UserProfileUpdate(BaseModel):
    first_name: constr(min_length=2, max_length=15, regex=r"^[A-Za-z ]+$")
    last_name: constr(min_length=2, max_length=15, regex=r"^[A-Za-z ]+$")
    email: EmailStr
    phone_number: constr(min_length=7, max_length=15, regex=r"^[0-9]+$")
    #university: constr(min_length=2, max_length=50)

EMAIL_CHANGE_COOLDOWN_DAYS = 90  # 3 months

from datetime import datetime, timedelta

@router.put("/{university}/{student_id}/profile")
async def update_user_profile(university: str, student_id: str, update: UserProfileUpdate):
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    now = datetime.utcnow()

    # Email cooldown check
    if update.email and update.email != data.get("email"):
        last_change_str = data.get("last_email_change")
        if last_change_str:
            try:
                last_change = datetime.fromisoformat(last_change_str)
                if now < last_change + timedelta(days=EMAIL_CHANGE_COOLDOWN_DAYS):
                    remaining = (last_change + timedelta(days=EMAIL_CHANGE_COOLDOWN_DAYS)) - now
                    raise HTTPException(
                        status_code=403,
                        detail=f"Email can only be changed again after {remaining.days} days."
                    )
            except Exception:
                pass  # malformed date, allow change

        # Update email + history (append safely)
        history = data.get("email_history", [])
        history.append({
            "old_email": data.get("email"),
            "new_email": update.email,
            "changed_at": now.isoformat()
        })
        doc_ref.update({
            "email": update.email,
            "last_email_change": now.isoformat(),
            "email_history": history
        })

    # Update other profile fields
    doc_ref.set({
        "first_name": update.first_name,
        "last_name": update.last_name,
        "phone_number": update.phone_number,
        "full_name": f"{update.first_name} {update.last_name}",
        "last_updated": now.isoformat()
    }, merge=True)

    return {
        "student_id": student_id,
        "university": university,
        "full_name": f"{update.first_name} {update.last_name}",
        "email": update.email,
        "message": f"Profile updated successfully. Next email change allowed after {(now + timedelta(days=EMAIL_CHANGE_COOLDOWN_DAYS)).strftime('%A, %d %B %Y')}."
    }


from datetime import datetime, timedelta, timezone

EMAIL_CHANGE_COOLDOWN_DAYS = 90  # ~3 months

@router.put("/admin/{university}/{student_id}/email")
async def admin_update_email(university: str, student_id: str, new_email: EmailStr, current_admin: dict = Depends(get_current_admin)):
    """
    Admin-only endpoint to update a student's email.
    Enforces a 3-month cooldown between changes.
    """
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    last_change_str = data.get("last_email_change")
    if last_change_str:
        try:
            last_change = datetime.fromisoformat(last_change_str)
            now = datetime.now(timezone.utc)
            if now < last_change + timedelta(days=EMAIL_CHANGE_COOLDOWN_DAYS):
                remaining = (last_change + timedelta(days=EMAIL_CHANGE_COOLDOWN_DAYS)) - now
                raise HTTPException(
                    status_code=403,
                    detail=f"Email can only be changed again after {remaining.days} days."
                )
        except Exception:
            pass  # malformed date, allow change

    # Save new email + timestamp
    now = datetime.now(timezone.utc)
    doc_ref.set({
        "email": new_email,
        "last_email_change": now.isoformat()
    }, merge=True)

    return {
        "student_id": student_id,
        "university": university,
        "email": new_email,
        "message": f"Email updated successfully. Next change allowed after {(now + timedelta(days=EMAIL_CHANGE_COOLDOWN_DAYS)).strftime('%A, %d %B %Y')}."
    }




@router.get("/{university}/{student_id}/profile/email-history")
async def get_email_history(
    university: str,
    student_id: str,
    since: str | None = Query(None, description="ISO date string to filter history (e.g. 2025-01-01)"),
    current_user: dict = Depends(get_current_user)
):
    """
    Return the email change history for a student.
    Optional `since` query param filters changes after a given date.
    """
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    history = data.get("email_history", [])

    # Apply filter if `since` provided
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            history = [h for h in history if datetime.fromisoformat(h["changed_at"]) >= since_dt]
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid 'since' date format. Use ISO format (YYYY-MM-DD).")

    return {
        "student_id": student_id,
        "university": university,
        "email_history": history,
        "message": f"Found {len(history)} email change record(s) for student {student_id} at {university}."
    }


class EmailRevertRequest(BaseModel):
    email: EmailStr
@router.post("/admin/{university}/{student_id}/email/revert")
async def admin_revert_email(
    university: str,
    student_id: str,
    request: EmailRevertRequest,
    current_admin: dict = Depends(get_current_admin)
):
    """
    Admin-only endpoint to revert a student's email to a previous one from history.
    """
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    history = data.get("email_history", [])
    matching_records = [h for h in history if h["old_email"] == request.email]

    if not matching_records:
        raise HTTPException(status_code=404, detail="Requested email not found in change history")

    # Revert email
    now = datetime.utcnow()
    doc_ref.set({
        "email": request.email,
        "last_email_change": now.isoformat()
    }, merge=True)

    return {
        "student_id": student_id,
        "university": university,
        "email": request.email,
        "message": f"Email reverted successfully to {request.email} for student {student_id} at {university}."
    }





class EmailRevertRequest(BaseModel):
    revert_to: EmailStr

@router.put("/admin/{university}/{student_id}/email/revert")
async def admin_revert_email(
    university: str,
    student_id: str,
    request: EmailRevertRequest,
    current_admin: dict = Depends(get_current_admin)  # ✅ only admins can call
):
    """
    Admin-only endpoint to revert a student's email to a previous one from history.
    """
    doc_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    history = data.get("email_history", [])

    # Ensure requested email exists in history
    if not any(h["new_email"] == request.revert_to or h["old_email"] == request.revert_to for h in history):
        raise HTTPException(status_code=400, detail="Requested email not found in history")

    now = datetime.utcnow()

    # Update email + log revert
    doc_ref.update({
        "email": request.revert_to,
        "last_email_change": now.isoformat(),
        "email_history": firestore.ArrayUnion([{
            "old_email": data.get("email"),
            "new_email": request.revert_to,
            "changed_at": now.isoformat(),
            "action": "revert"
        }])
    })

    return {
        "student_id": student_id,
        "university": university,
        "email": request.revert_to,
        "message": f"Email reverted successfully to {request.revert_to} by admin."
    }



@router.get("/{university}/{student_id}/feed")
async def get_student_feed(university: str, student_id: str):
    await assert_student_exists(university, student_id)

    events_ref = (
        db.collection("yearbook")
          .document(university)
          .collection(student_id)
          .collection("events")
    )

    feed = []
    docs = list(events_ref.stream())
    if not docs:
        return {"items": [], "message": "No events found yet for this student"}

    for doc in docs:
        data = doc.to_dict() or {}
        event_id = doc.id
        photo_urls = data.get("photo_urls", [])
        likes = data.get("likes", [])
        uploaded_at = data.get("uploaded_at", "")

        feed.append({
            "event_id": event_id,
            "event_name": data.get("linked_event_id", event_id),
            "photos": photo_urls,              # ✅ renamed to match Flutter
            "likes_count": len(likes),
            "liked": False,                    # ✅ default until toggle endpoint updates
            "uploaded_at": uploaded_at,
        })

    feed.sort(key=lambda x: x["uploaded_at"], reverse=True)
    return {"items": feed}


# ===============================
# MESSAGES
# ===============================
# ===============================
# MESSAGE ENDPOINTS
# ===============================

@router.get("/messages/{university}/{student_id}")
async def get_messages(university: str, student_id: str, current_user: dict = Depends(get_student_or_admin)):
    try:
        assert_owns_resource_or_admin(current_user, university, student_id)

        # ✅ FIXED PATH: Collection -> Doc -> Collection -> Doc -> Collection
        messages_ref = (
            db.collection("MESSAGES")
              .document(university)
              .collection("students") 
              .document(student_id)    
              .collection("messages")  
              .order_by("timestamp", direction=firestore.Query.DESCENDING)
        )

        docs = list(messages_ref.stream())

        messages = []
        for doc in docs:
            data = doc.to_dict() or {}
            messages.append({
                "id": doc.id,
                "title": data.get("title", ""),
                "body": data.get("body", ""),
                "timestamp": data.get("timestamp"),
                "read": data.get("read", False),
                "type": data.get("type", "system"),
            })

        return messages  # Returns the List Flutter expects

    except Exception as e:
        logger.exception("Error fetching messages")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/messages/{university}/{student_id}/{message_id}/read")
async def mark_message_read(
    university: str,
    student_id: str,
    message_id: str,
    current_user: dict = Depends(get_student_or_admin),
):
    try:
        assert_owns_resource_or_admin(current_user, university, student_id)
        
        # ✅ FIXED PATH: Added .collection("students") and .document(student_id)
        msg_ref = (
            db.collection("MESSAGES")
              .document(university)
              .collection("students")
              .document(student_id)
              .collection("messages")
              .document(message_id)
        )

        doc = msg_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Message not found")

        msg_ref.update({"read": True})
        return {"status": "ok", "message_id": message_id}

    except Exception as e:
        logger.exception("Error in mark_message_read")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ===============================
# MESSAGE HELPERS
# ===============================

def log_premium_message(university: str, student_id: str, premium_expires: str):
    """
    Helper to send a message to a student. 
    Crucial: Must use the same path as the GET/PUT routes!
    """
    now = datetime.utcnow().isoformat()

    message_data = {
        "title": "Premium Activated",
        "body": f"Your premium subscription is active until {premium_expires}.",
        "timestamp": now,
        "read": False,
        "type": "payment",
    }

    # ✅ FIXED PATH: Correct hierarchy for writing data
    (
        db.collection("MESSAGES")
          .document(university)
          .collection("students")
          .document(student_id)
          .collection("messages")
          .add(message_data)
    )






@router.post("/event/{university}/{event_id}/like")
async def toggle_like_event(
    university: str,
    event_id: str,
    current_user: dict = Depends(get_current_user)
):
    viewer_id = current_user["user_id"]

    event_ref = (
        db.collection("yearbook")
          .document(university)
          .collection(viewer_id)   # OR student owner, depending on your model
          .collection("events")
          .document(event_id)
    )

    doc = event_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Event not found")

    data = doc.to_dict()
    likes = set(data.get("likes", []))

    if viewer_id in likes:
        likes.remove(viewer_id)
        liked = False
    else:
        likes.add(viewer_id)
        liked = True

    event_ref.update({"likes": list(likes)})

    return {
        "liked": liked,
        "likes_count": len(likes),
    }

