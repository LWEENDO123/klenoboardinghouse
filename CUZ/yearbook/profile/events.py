from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Body
from typing import List, Optional
from datetime import datetime
import random

# ✅ Routers inside CUZ
from CUZ.routers.region_router import recalculate_origin

# ✅ Core modules inside CUZ/core
from CUZ.core.firebase import db
from firebase_admin import messaging
from CUZ.core.security import get_student_or_admin, get_student_union_or_higher

# ✅ Event models (adjust depending on your folder structure)
# If models are in CUZ/Event/models.py:
from CUZ.yearbook.profile.model import Event, EventResponse


# Or if they’re in CUZ/yearbook/Event/models.py:
# from CUZ.yearbook.Event.models import Event, EventResponse

# ✅ Local utilities (relative imports inside yearbook/profile/)
from .security import validate_image
from .compress import compress_to_720
from .compress import upload_to_firebase
from .identity import assert_student_exists, assert_owns_resource_or_admin
from .event_utils import assert_event_portal_open, today_event_id


router = APIRouter(prefix="/event", tags=["Events"])


# ============================================================
# 🔹 CREATE EVENTS (Scoped / Global / Union)
# ============================================================

@router.post("/{university}/create", response_model=dict)
async def create_event(
    university: str,
    event: Event,
    scope: str = Query("scoped", enum=["scoped", "global", "union"]),
    current_user: dict = Depends(get_student_union_or_higher)
):
    """Create an event (scoped/global/union) and notify students."""
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    try:
        # ✅ Generate unique event ID
        event_id = f"{event.title[0].upper()}{datetime.now().strftime('%m%d%Y')}{random.randint(100000,999999)}"
        event_data = event.dict()
        event_data["created_by"] = current_user["user_id"]
        event_data["scope"] = scope

        # ✅ Scoped storage
        db.collection("Yearbook").document("profile").collection("events").document(university).collection("events").document(event_id).set(event_data)

        # ✅ Global replication if needed
        if scope in ["global", "union"]:
            from core.config import CLUSTERS
            if university in CLUSTERS:
                for uni in CLUSTERS[university]:
                    db.collection("Yearbook").document("profile").collection("events").document(uni).collection("events").document(event_id).set(event_data)

        # ✅ Notification payload
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
        db.collection("USERS").document(university).collection("notifications").add(notif_data)

        # ✅ FCM broadcast
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=notif_data["title"],
                    body=notif_data["body"]
                ),
                topic=f"university_{university}",
                data={"event_id": event_id}
            )
            fcm_response = messaging.send(message)
        except Exception as e:
            print(f"Notification error: {e}")
            fcm_response = None

        return {
            "message": f"✅ {scope.capitalize()} event created",
            "event_id": event_id,
            "data": event_data,
            "fcm_response": fcm_response
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating event: {str(e)}")


# ============================================================
# 🔹 STUDENT UPLOADS (Photos + Q&A) — AUTO-LINK TO TODAY'S EVENT
# ============================================================

@router.post("/{university}/{student_id}/upload")
async def upload_student_event_photos(
    university: str,
    student_id: str,
    files: List[UploadFile] = File(...),
    category: Optional[str] = None,
    qna: Optional[List[dict]] = Body(None),
    current_user: dict = Depends(get_student_or_admin)
):
    """Student uploads photos/Q&A automatically linked to today's event for their university."""
    # ✅ Identity checks
    assert_owns_resource_or_admin(current_user, university, student_id)
    await assert_student_exists(university, student_id)

    # ✅ Automatically resolve today's event ID
    event_id = today_event_id()
    assert_event_portal_open(university, event_id)

    if len(files) > 5:
        raise HTTPException(status_code=400, detail="Max 5 photos allowed per event")

    # ✅ Process and upload photos
    photo_urls = []
    for file in files:
        raw = await file.read()
        validate_image(raw, file.filename)
        compressed = compress_to_720(raw)
        url = upload_compressed_image(
            university,
            student_id,
            compressed,
            f"{student_id}_{event_id}_{file.filename}",
            public=False
        )
        photo_urls.append(url)

    now = datetime.utcnow().isoformat()

    # ✅ Check if event is final_semester
    event_doc = (
        db.collection("Yearbook")
          .document("profile")
          .collection("events")
          .document(university)
          .collection("events")
          .document(event_id)
          .get()
    )
    if not event_doc.exists:
        raise HTTPException(status_code=404, detail="Event not found")
    event_data = event_doc.to_dict()
    is_final_semester = event_data.get("final_semester", False)

    # ✅ Save under student's yearbook profile
    event_ref = (
        db.collection("yearbook")
          .document(university)
          .collection("students")
          .document(student_id)
          .collection("events")
          .document(event_id)
    )

    save_data = {
        "student_id": student_id,
        "photo_urls": photo_urls,
        "category": category or "university",
        "linked_event_id": event_id,
        "uploaded_at": now,
        "final_semester": is_final_semester
    }
    if is_final_semester and qna:
        save_data["qna"] = qna

    event_ref.set(save_data, merge=True)

    # ✅ Personal confirmation notification
    try:
        notif_title = "Upload Successful"
        notif_body = (
            f"Your final semester photos and Q&A for {event_data.get('title')} were uploaded successfully."
            if is_final_semester else
            f"Your photos for {event_data.get('title')} were uploaded successfully."
        )
        target_token = current_user.get("fcm_token")
        if target_token:
            message = messaging.Message(
                notification=messaging.Notification(title=notif_title, body=notif_body),
                token=target_token,
                data={"event_id": event_id}
            )
            messaging.send(message)
    except Exception as e:
        print(f"⚠️ Notification failed: {e}")

    return {
        "event_id": event_id,
        "photo_urls": photo_urls,
        "category": category,
        "final_semester": is_final_semester,
        "qna": qna if is_final_semester else None
    }


# ============================================================
# 🔹 STUDENT LISTING (Fetch uploads)
# ============================================================
@router.get("/{university}/{student_id}/list")
async def list_student_event_photos(
    university: str,
    student_id: str,
    category: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    current_user: dict = Depends(get_student_or_admin),
):
    assert_owns_resource_or_admin(current_user, university, student_id)

    try:
        # ✅ CORRECTED PATH: Collection -> Document -> Collection -> Document -> Collection
        events_ref = (
            db.collection("yearbook")
              .document(university)
              .collection("students") # 1. Added this collection layer
              .document(student_id)    # 2. Changed this to a document
              .collection("events")    # 3. Now this works!
        )

        items = []
        for doc in events_ref.stream():
            data = doc.to_dict() or {}
            uploaded_at = data.get("uploaded_at", "")

            if category and data.get("category") != category:
                continue
            if year and not uploaded_at.startswith(str(year)):
                continue

            items.append({
                "event_id": doc.id,
                "event_name": data.get("linked_event_id", doc.id),
                "photos": data.get("photo_urls", []),
                "likes_count": len(data.get("likes", [])),
                "liked": current_user.get("user_id") in data.get("likes", []),
                "uploaded_at": uploaded_at,
                "final_semester": data.get("final_semester", False),
                "qna": data.get("qna"),
            })

        items.sort(key=lambda x: x["uploaded_at"], reverse=True)

        return {
            "student_id": student_id,
            "items": items
        }

    except Exception as e:
        print("❌ list_student_event_photos error:", e)
        # Detailed error for debugging
        raise HTTPException(status_code=500, detail=f"Firestore path error: {str(e)}")



# ============================================================
# 🔹 STUDENT: GET EVENTS (Paginated)
# ============================================================

@router.get("/{university}/list", response_model=dict)
async def get_events(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_student_or_admin)
):
    """Fetch paginated events for a university (free for all authenticated students)."""
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")

    try:
        events_ref = (
            db.collection("Yearbook")
              .document("profile")
              .collection("events")
              .document(university)
              .collection("events")
              .get()
        )

        events = []
        for doc in events_ref:
            data = doc.to_dict()
            event_summary = {
                "id": doc.id,
                "title": data.get("title"),
                "date": data.get("date"),
                "time": data.get("time"),
                "location": data.get("location"),
                "image_url": data.get("image_url"),
                "university": data.get("university"),
                "created_by": data.get("created_by")
            }
            events.append(event_summary)

        total = len(events)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated_data = events[start:end]

        return {
            "data": paginated_data,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching events: {str(e)}")


# ============================================================
# 🔹 STUDENT: GET CLUSTER EVENTS
# ============================================================

@router.get("/cluster/{university}", response_model=dict)
async def get_cluster_events(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_student_or_admin)
):
    """Fetch events for all universities in the same cluster as the given university."""
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")

    try:
        cluster_unis = CLUSTERS.get(university, [university])
        events = []

        for uni in cluster_unis:
            docs = (
                db.collection("Yearbook")
                  .document("profile")
                  .collection("events")
                  .document(uni)
                  .collection("events")
                  .get()
            )
            for doc in docs:
                data = doc.to_dict()
                event_summary = {
                    "id": doc.id,
                    "title": data.get("title"),
                    "date": data.get("date"),
                    "time": data.get("time"),
                    "location": data.get("location"),
                    "image_url": data.get("image_url"),
                    "university": data.get("university"),
                    "created_by": data.get("created_by")
                }
                events.append(event_summary)

        total = len(events)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated_data = events[start:end]

        return {
            "data": paginated_data,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cluster events: {str(e)}")




# ============================================================
# 🔹 STUDENT: GET GOOGLE DIRECTIONS (with recalculation)
# ============================================================
@router.get("/{university}/{event_id}/directions/google")
async def get_event_google_directions(
    university: str,
    event_id: str,
    student_id: str,
    current_lat: float = Query(...),
    current_lon: float = Query(...),
    region: Optional[str] = Query(None, description="Optional region hub for recalculation"),
    current_user: dict = Depends(get_student_or_admin)
):
    """Generate Google Maps deep link for event directions (free for all students)."""
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")

    # ✅ Updated Firestore path
    event_ref = (
        db.collection("Yearbook")
          .document("profile")
          .collection("events")
          .document(university)
          .collection("events")
          .document(event_id)
          .get()
    )
    if not event_ref.exists:
        raise HTTPException(status_code=404, detail="Event not found")

    data = event_ref.to_dict()
    gps_coordinates = data.get("GPS_coordinates")
    if not gps_coordinates or len(gps_coordinates) != 2:
        raise HTTPException(status_code=400, detail="GPS coordinates not available")

    # ✅ Use shared recalculation logic
    new_lat, new_lon = recalculate_origin(current_lat, current_lon, region)

    maps_link = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={new_lat},{new_lon}"
        f"&destination={gps_coordinates[0]},{gps_coordinates[1]}"
        f"&travelmode=driving"
    )
    return {
        "link": maps_link,
        "service": "google_maps",
        "adjusted_origin": [new_lat, new_lon],
        "region": region or "none"
    }


# ============================================================
# 🔹 STUDENT: GET YANGO DIRECTIONS (with recalculation)
# ============================================================
@router.get("/{university}/{event_id}/directions/yango")
async def get_event_yango_directions(
    university: str,
    event_id: str,
    student_id: str,
    current_lat: float = Query(...),
    current_lon: float = Query(...),
    region: Optional[str] = Query(None, description="Optional region hub for recalculation"),
    current_user: dict = Depends(get_student_or_admin)
):
    """Generate Yango deep link for event directions (free for all students)."""
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")

    # ✅ Updated Firestore path
    event_ref = (
        db.collection("Yearbook")
          .document("profile")
          .collection("events")
          .document(university)
          .collection("events")
          .document(event_id)
          .get()
    )
    if not event_ref.exists:
        raise HTTPException(status_code=404, detail="Event not found")

    data = event_ref.to_dict()
    yango_coordinates = data.get("yango_coordinates")
    if not yango_coordinates or len(yango_coordinates) != 2:
        raise HTTPException(status_code=400, detail="Yango coordinates not available")

    # ✅ Use shared recalculation logic
    new_lat, new_lon = recalculate_origin(current_lat, current_lon, region)

    browser_link = (
        f"https://yango.com/en_int/order/"
        f"?gfrom={new_lat},{new_lon}"
        f"&gto={yango_coordinates[0]},{yango_coordinates[1]}"
        f"&tariff=econom&lang=en"
    )
    deep_link = (
        f"yango://route?"
        f"start-lat={new_lat}&start-lon={new_lon}"
        f"&end-lat={yango_coordinates[0]}&end-lon={yango_coordinates[1]}"
    )

    return {
        "browser_link": browser_link,
        "deep_link": deep_link,
        "service": "yango",
        "adjusted_origin": [new_lat, new_lon],
        "region": region or "none"
    }

