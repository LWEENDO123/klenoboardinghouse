from fastapi import APIRouter, Depends, HTTPException, Query, Request, Body
from typing import Optional
from datetime import datetime, timezone
import math
import uuid

from core.firebase import db
from core.security import get_premium_student_or_admin
from firebase_admin import firestore as admin_fs
from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter(prefix="/tracking", tags=["kleno-tracking"])
limiter = Limiter(key_func=get_remote_address)

# ... keep existing utilities, config, parse_iso, _tracking_root, start_session, log_breadcrumb ...

def _get_boardinghouse_coords(university: str, boardinghouse_id: str):
    """
    Resolve destination coordinates for a boarding house:
    Tries BOARDINGHOUSES/{id} first, then HOME/{university}/BOARDHOUSE/{id}.
    Returns (lat, lon) or raises HTTPException.
    """
    ref = db.collection("BOARDINGHOUSES").document(boardinghouse_id).get()
    if not ref.exists:
        ref = db.collection("HOME").document(university).collection("BOARDHOUSE").document(boardinghouse_id).get()
    if not ref.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    bh = ref.to_dict() or {}
    dest = bh.get("yango_coordinates") or bh.get("GPS_coordinates")
    if not dest or len(dest) != 2:
        raise HTTPException(status_code=400, detail="Destination coordinates missing")
    return float(dest[0]), float(dest[1])

def _get_student_stored_location(university: str, student_id: str):
    """
    Fetch student’s stored lat/lon from USERS/{university}/students/{student_id}.
    """
    sref = db.collection("USERS").document(university).collection("students").document(student_id).get()
    if not sref.exists:
        raise HTTPException(status_code=404, detail="Student not found")
    s = sref.to_dict() or {}
    lat, lon = s.get("lat"), s.get("lon")
    if lat is None or lon is None:
        raise HTTPException(status_code=404, detail="No stored location. Provide current_lat/current_lon.")
    return float(lat), float(lon)

@router.post("/start/by-house")
async def start_session_by_house(
    university: str = Body(...),
    student_id: str = Body(...),
    boardinghouse_id: str = Body(...),
    current_lat: Optional[float] = Body(None),
    current_lon: Optional[float] = Body(None),
    note: Optional[str] = Body(None),
    current_user: dict = Depends(get_premium_student_or_admin),
):
    """
    Start tracking using a boardinghouse_id. If current_lat/lon are omitted,
    uses the student’s stored profile location as origin.
    """
    # Identity enforcement
    if current_user.get("role") == "student":
        if student_id != current_user.get("user_id") or university != current_user.get("university"):
            raise HTTPException(status_code=403, detail="Identity mismatch")

    # Resolve destination
    dest_lat, dest_lon = _get_boardinghouse_coords(university, boardinghouse_id)

    # Resolve origin: provided or stored
    if current_lat is None or current_lon is None:
        current_lat, current_lon = _get_student_stored_location(university, student_id)

    # Compute straight distance, R0
    straight_km = haversine_km(current_lat, current_lon, dest_lat, dest_lon)
    R0 = max(2.0, straight_km + 2.0)
    radius_km = R0
    started_at_iso = now_iso()

    # Create new session
    session_id = uuid.uuid4().hex
    root = _tracking_root(university, student_id)
    session_ref = root.collection("sessions").document(session_id)

    session_ref.set({
        "session_id": session_id,
        "university": university,
        "user_id": student_id,
        "boardinghouse_id": boardinghouse_id,
        "started_at": started_at_iso,
        "status": "active",
        "origin": {"lat": current_lat, "lon": current_lon},
        "destination": {"lat": dest_lat, "lon": dest_lon},
        "distance_km_straight": round(straight_km, 3),
        "bubble": {
            "center": {"lat": dest_lat, "lon": dest_lon},
            "radius_km": round(radius_km, 3),
            "R0_km": round(R0, 3),
            "min_radius_km": MIN_RADIUS_KM,
            "shrink_step_km": SHRINK_STEP_KM,
            "shrink_interval_min": SHRINK_INTERVAL_MIN,
            "last_shrink_at": started_at_iso,
            "shrink_step_count": 0,
            "cardinal": {d: round(radius_km, 3) for d in ["N_km", "S_km", "E_km", "W_km"]},
        },
        "client_note": note,
        "breadcrumbs": [{
            "lat": current_lat,
            "lon": current_lon,
            "captured_at": started_at_iso,
            "distance_to_dest_km": round(straight_km, 3),
            "bubble_radius_km": round(radius_km, 3),
            "allowed_dev_km": round(LATERAL_ALLOWANCE_RATIO * radius_km, 3),
            "heading": direction_label(bearing(current_lat, current_lon, current_lat, current_lon)),
            "movement": "start",
        }],
        "metrics": {
            "points_logged": 1,
            "max_deviation_km": 0.0,
            "last_distance_km": round(straight_km, 3),
            "last_deviation_km": 0.0,
        },
        "alerts": [],
        "bubble_history": [{
            "at": started_at_iso,
            "radius_km": round(radius_km, 3),
            "reason": "init",
        }],
    })

    root.collection("index").document(session_id).set({
        "session_id": session_id,
        "status": "active",
        "started_at": started_at_iso,
        "boardinghouse_id": boardinghouse_id,
        "distance_km_straight": round(straight_km, 3),
        "bubble_radius_km": round(radius_km, 3),
    })

    return {
        "message": "Tracking session started",
        "session_id": session_id,
        "bubble_radius_km": round(radius_km, 3),
        "distance_km_straight": round(straight_km, 3),
        "destination": [dest_lat, dest_lon],
        "origin": [current_lat, current_lon],
    }

@router.post("/{university}/{student_id}/sessions/{session_id}/resume/by-house")
@limiter.limit("2/30seconds")
async def resume_session_by_house(
    request: Request,
    university: str,
    student_id: str,
    session_id: str,
    boardinghouse_id: str = Body(...),
    current_lat: Optional[float] = Body(None),
    current_lon: Optional[float] = Body(None),
    current_user: dict = Depends(get_premium_student_or_admin),
):
    """
    Resume an active session and rebind destination to a new/confirmed boarding house.
    Logs a breadcrumb with current position (provided or fetched from student’s stored location)
    and recomputes the bubble radius with the stepped shrink + safety floor.
    """
    # Identity enforcement
    if current_user.get("role") == "student":
        if student_id != current_user.get("user_id") or university != current_user.get("university"):
            raise HTTPException(status_code=403, detail="Identity mismatch")

    # Fetch session
    root = _tracking_root(university, student_id)
    session_ref = root.collection("sessions").document(session_id)
    snap = session_ref.get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Session not found")
    session = snap.to_dict()
    if session.get("status") != "active":
        raise HTTPException(status_code=400, detail="Session not active")

    # Resolve destination from boardinghouse_id
    dest_lat, dest_lon = _get_boardinghouse_coords(university, boardinghouse_id)

    # Resolve current position (provided or stored)
    if current_lat is None or current_lon is None:
        current_lat, current_lon = _get_student_stored_location(university, student_id)

    # Compute distances
    d_km = haversine_km(current_lat, current_lon, dest_lat, dest_lon)
    origin = session.get("origin", {"lat": current_lat, "lon": current_lon})
    dev_km = point_to_segment_distance(current_lat, current_lon, origin["lat"], origin["lon"], dest_lat, dest_lon)
    max_dev = max(float(session["metrics"].get("max_deviation_km", 0.0)), dev_km)

    # Bubble stepped shrink with safety floor
    bubble = session.get("bubble", {})
    R0 = float(bubble.get("R0_km", d_km + 2.0))
    prev_radius = float(bubble.get("radius_km", R0))

    started_at_iso = session.get("started_at")
    elapsed_minutes = 0.0
    if started_at_iso:
        try:
            started_at = parse_iso(started_at_iso)
            elapsed_minutes = (datetime.now(timezone.utc) - started_at).total_seconds() / 60.0
        except Exception:
            elapsed_minutes = 0.0

    n_steps = int(elapsed_minutes // SHRINK_INTERVAL_MIN)
    candidate_radius = R0 - n_steps * SHRINK_STEP_KM
    radius_km = max(MIN_RADIUS_KM, d_km + SAFETY_MARGIN_KM, candidate_radius)
    allowed_dev_km = LATERAL_ALLOWANCE_RATIO * radius_km

    # Direction and movement
    bearing_angle = bearing(origin["lat"], origin["lon"], current_lat, current_lon)
    heading = direction_label(bearing_angle)
    prev_dist = float(session["metrics"].get("last_distance_km", d_km))
    movement = "closer to destination" if d_km < prev_dist else "away from destination"

    point = {
        "lat": current_lat,
        "lon": current_lon,
        "captured_at": now_iso(),
        "distance_to_dest_km": round(d_km, 3),
        "deviation_km": round(dev_km, 3),
        "heading": heading,
        "movement": movement,
        "bubble_radius_km": round(radius_km, 3),
        "allowed_dev_km": round(allowed_dev_km, 3),
    }

    alerts = []
    if dev_km > allowed_dev_km and dev_km < 1.0:
        alerts.append(
            f"⚠️ Soft warning: {round(dev_km*1000)}m off corridor (allowed ≤ {round(allowed_dev_km*1000)}m), heading {heading}, moving {movement}"
        )
    elif dev_km >= 1.0:
        alerts.append(
            f"🚨 Hard warning: {round(dev_km,2)}km off corridor (allowed ≤ {round(allowed_dev_km,2)}km), heading {heading}, moving {movement}"
        )

    prev_dev = float(session["metrics"].get("last_deviation_km", 0.0))
    if prev_dev > allowed_dev_km and dev_km <= allowed_dev_km:
        alerts.append(
            f"✅ Returning: within lateral allowance again (≤ {round(allowed_dev_km*1000)}m), heading {heading}, moving {movement}"
        )

    # Update destination and bubble
    cardinal = {d: round(radius_km, 3) for d in ["N_km", "S_km", "E_km", "W_km"]}

    updates = {
        "destination": {"lat": dest_lat, "lon": dest_lon},
        "boardinghouse_id": boardinghouse_id,
        "breadcrumbs": admin_fs.ArrayUnion([point]),
        "metrics.points_logged": admin_fs.Increment(1),
        "metrics.max_deviation_km": round(max_dev, 3),
        "metrics.last_deviation_km": round(dev_km, 3),
        "metrics.last_distance_km": round(d_km, 3),
        "last_updated_at": now_iso(),
        "bubble.radius_km": round(radius_km, 3),
        "bubble.cardinal": cardinal,
        "bubble.shrink_step_count": n_steps,
        "bubble.shrink_step_km": SHRINK_STEP_KM,
        "bubble.shrink_interval_min": SHRINK_INTERVAL_MIN,
        "bubble.min_radius_km": MIN_RADIUS_KM,
    }

    if round(radius_km, 3) != round(prev_radius, 3):
        updates.setdefault("bubble_history", admin_fs.ArrayUnion([{
            "at": now_iso(),
            "radius_km": round(radius_km, 3),
            "prev_radius_km": round(prev_radius, 3),
            "steps_elapsed": n_steps,
            "reason": "stepped_shrink_with_safety_floor",
        }]))
        updates["bubble.last_shrink_at"] = now_iso()

    session_ref.update(updates)

    if alerts:
        session_ref.update({"alerts": admin_fs.ArrayUnion(alerts)})
    else:
        session_ref.update({"alerts": admin_fs.ArrayUnion([])})

    return {
        "message": "Session resumed and breadcrumb logged",
        "destination": [dest_lat, dest_lon],
        "distance_to_dest_km": round(d_km, 3),
        "deviation_km": round(dev_km, 3),
        "bubble_radius_km": round(radius_km, 3),
        "allowed_dev_km": round(allowed_dev_km, 3),
        "alerts": alerts
    }
