# Proxylocation/alert.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
import requests

from CUZ.core.firebase import db
from firebase_admin import messaging
from CUZ.Proxylocation.ssecurity import get_premium_student_or_admin
from CUZ.core.config import CLUSTERS
from CUZ.routers.region_router import recalculate_origin


router = APIRouter(prefix="/proxily", tags=["proxily"])


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """
    Use OpenStreetMap Nominatim to get a human-readable address.
    """
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
        resp = requests.get(url, headers={"User-Agent": "baodinghouse-app"})
        if resp.status_code == 200:
            data = resp.json()
            return data.get("display_name") or None
    except Exception as e:
        print(f"Reverse geocode error: {e}")
    return None


@router.post("/alert/{university}")
async def send_alert(
    university: str,
    student_id: str,
    message: Optional[str] = None,       # Optional custom message
    boardinghouse_id: Optional[str] = None,
    use_region_anchor: bool = Query(True, description="Snap/fine-tune origin via regional anchor if available"),
    region: Optional[str] = Query(None, description="Optional region name (defaults to student's university)"),
    current_user: dict = Depends(get_premium_student_or_admin)
):
    """
    Send an alert to all landlords in the student's cluster (premium students only).
    - Enforces max 2 alerts per student per day.
    - Expands to all universities in the same cluster.
    - Fetches student's first and last name to personalize the broadcast.
    - Includes student's origin coordinates (raw + adjusted) and reverse-geocoded address.
    - Sends FCM notification to landlords in each university.
    - Stores alert in USERS/{university}/alerts.
    """

    # ✅ Validate student identity
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")

    try:
        # ✅ Enforce daily limit (2 per day)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        alerts_query = (
            db.collection("USERS")
            .document(university)
            .collection("alerts")
            .where("student_id", "==", student_id)
            .where("timestamp", ">=", today_start)
            .get()
        )
        if len(alerts_query) >= 2:
            raise HTTPException(status_code=403, detail="Daily alert limit reached (2 per day)")

        # ✅ Fetch student's profile
        student_doc = (
            db.collection("USERS")
            .document(university)
            .collection("students")
            .document(student_id)
            .get()
        )
        if not student_doc.exists:
            raise HTTPException(status_code=404, detail="Student not found")
        student_data = student_doc.to_dict()
        first_name = student_data.get("first_name", "A student")
        last_name = student_data.get("last_name", "")

        # ✅ Resolve origin coordinates
        origin_lat, origin_lon = student_data.get("lat"), student_data.get("lon")
        if origin_lat is None or origin_lon is None:
            raise HTTPException(status_code=404, detail="No stored location. Please update your location.")

        effective_region = region or university
        adj_lat, adj_lon = origin_lat, origin_lon
        if use_region_anchor:
            adj_lat, adj_lon = recalculate_origin(origin_lat, origin_lon, effective_region)

        # ✅ Reverse-geocode adjusted coordinates
        display_address = reverse_geocode(adj_lat, adj_lon) or "Unknown location"

        # ✅ Build broadcast message
        broadcast_message = (
            f"{first_name} {last_name} is looking for a boarding house near {display_address}. "
            f"Update your listings so that they can see it."
        )
        if message:
            broadcast_message += f" Note: {message}"

        # ✅ Find cluster universities
        region_universities = CLUSTERS.get(university, [university])
        if not region_universities:
            raise HTTPException(status_code=404, detail=f"University {university} not mapped to any cluster")

        sent_to = []
        for univ in region_universities:
            # ✅ Send FCM notification to landlords channel
            topic = f"landlords_{univ}"
            fcm_message = messaging.Message(
                notification=messaging.Notification(
                    title="Student Alert",
                    body=broadcast_message
                ),
                topic=topic,
                data={
                    "student_id": student_id,
                    "boardinghouse_id": boardinghouse_id or "",
                    "origin_university": university,
                    "origin_lat": str(origin_lat),
                    "origin_lon": str(origin_lon),
                    "adjusted_lat": str(adj_lat),
                    "adjusted_lon": str(adj_lon),
                    "origin_region": effective_region,
                    "display_address": display_address,
                }
            )
            fcm_response = messaging.send(fcm_message)

            # ✅ Store alert in Firestore
            alert_data = {
                "message": broadcast_message,
                "student_id": student_id,
                "boardinghouse_id": boardinghouse_id,
                "origin_university": university,
                "target_university": univ,
                "timestamp": datetime.utcnow(),
                "origin_lat": origin_lat,
                "origin_lon": origin_lon,
                "adjusted_lat": adj_lat,
                "adjusted_lon": adj_lon,
                "origin_region": effective_region,
                "display_address": display_address,
            }
            db.collection("USERS").document(univ).collection("alerts").add(alert_data)

            sent_to.append({"university": univ, "fcm_response": fcm_response})

        return {
            "message": "✅ Alert sent successfully to cluster",
            "cluster_universities": region_universities,
            "broadcast_message": broadcast_message,
            "origin_used": {
                "raw": [origin_lat, origin_lon],
                "adjusted": [adj_lat, adj_lon] if use_region_anchor else None,
                "region": effective_region if use_region_anchor else None,
                "display_address": display_address,
            },
            "details": sent_to
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending alert: {str(e)}")
