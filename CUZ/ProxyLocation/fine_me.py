# Proxylocation/fine_me.py
import math
from typing import List, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud import firestore

from CUZ.core.firebase import db
from CUZ.core.config import CLUSTERS
from CUZ.USERS.models import (
    BoardingHouseHomepage,
    BoardingHouseSummary,
    BoardingHouseNavigation,
)
from CUZ.core.security import get_student_or_admin, get_premium_student_or_admin
from CUZ.routers.region_router import recalculate_origin


# 🔗 Regional anchor recalculation
# Ensure routers is a proper package (routers/__init__.py present) and main.py registers it.
from CUZ.routers.region_router import recalculate_origin


router = APIRouter(prefix="/fine_me", tags=["ProxyLocation"])


# ==============================
# Utilities
# ==============================
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in meters between two lat/lon points."""
    R = 6371000  # meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def build_google_link(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> str:
    return (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_lat},{origin_lon}"
        f"&destination={dest_lat},{dest_lon}"
        f"&travelmode=driving"
    )


def build_yango_links(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> Dict[str, str]:
    return {
        "yango_browser": (
            f"https://yango.com/en_int/order/"
            f"?gfrom={origin_lat},{origin_lon}"
            f"&gto={dest_lat},{dest_lon}"
            f"&tariff=econom&lang=en"
        ),
        "yango_deep": (
            f"yango://route?"
            f"start-lat={origin_lat}&start-lon={origin_lon}"
            f"&end-lat={dest_lat}&end-lon={dest_lon}"
            f"&ref=proxy_location_app"
        ),
    }


# ==============================
# Get student's stored location
# ==============================
@router.get("/{university}/{student_id}", response_model=dict)
async def get_fine_me_location(
    university: str,
    student_id: str,
    current_user: dict = Depends(get_student_or_admin),
):
    # ✅ Identity checks
    if current_user.get("role") == "student" and student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    doc = (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
        .get()
    )
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    data = doc.to_dict()
    lat, lon = data.get("lat"), data.get("lon")
    if lat is None or lon is None:
        raise HTTPException(status_code=404, detail="Location not found. Please update your location.")

    return {
        "lat": lat,
        "lon": lon,
        "updated_at": data.get("location_updated_at") or "Unknown",
        "adjusted_origin": data.get("adjusted_origin"),  # optional auditing
    }


# ==============================
# Update student's stored location
# ==============================
@router.post("/{university}/{student_id}/update")
async def update_fine_me_location(
    university: str,
    student_id: str,
    lat: float,
    lon: float,
    current_user: dict = Depends(get_student_or_admin),
):
    # ✅ Identity checks
    if current_user.get("role") == "student" and student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    ref = (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
    )
    snapshot = ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Student not found")

    ref.update(
        {
            "lat": lat,
            "lon": lon,
            "location_updated_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return {"message": "Location updated successfully"}


# ==============================
# Homepage summary (lightweight cards)
# ==============================
@router.get("/{university}/{student_id}/home", response_model=dict)
async def get_homepage_summary(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(6, ge=1, le=24),
    current_user: dict = Depends(get_premium_student_or_admin),  # ✅ enforce premium
):
    # ✅ Identity checks
    if current_user.get("role") == "student" and student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    # ✅ Query Firestore
    docs = (
        db.collection("BOARDINGHOUSES")
        .where("universities", "array_contains", university)
        .get()
    )
    if not docs:
        docs = (
            db.collection("HOME")
            .document(university)
            .collection("BOARDHOUSE")
            .get()
        )

    total = len(docs)
    start = (page - 1) * limit
    end = min(start + limit, total)
    paginated = docs[start:end]

    homepage_data: List[BoardingHouseHomepage] = []

    for doc in paginated:
        data = doc.to_dict()

        # ✅ Compute lowest available price
        prices = [
            float(data.get("price_4", float("inf"))),
            float(data.get("price_3", float("inf"))),
            float(data.get("price_2", float("inf"))),
            float(data.get("price_1", float("inf"))),
        ]
        lowest_price = min([p for p in prices if p != float("inf")], default=float("inf"))
        price_str = str(lowest_price) if lowest_price != float("inf") else "N/A"

        # ✅ Pick best available image
        image = (
            data.get("image_4")
            or data.get("image_3")
            or data.get("image_2")
            or data.get("image_1")
            or "default_image.jpg"
        )

        # ✅ Resolve gender to model’s accepted variants
        gender = (
            "both"
            if data.get("gender_both")
            else "male"
            if data.get("gender_male")
            else "female"
            if data.get("gender_female")
            else "mixed"
        )

        homepage_data.append(
            BoardingHouseHomepage(
                id=doc.id,
                name_boardinghouse=data.get("name", "Unnamed"),
                price=price_str,
                image=image,
                gender=gender,
                location=data.get("location"),
                rating=data.get("rating"),
            )
        )

    return {
        "data": homepage_data,
        "total_pages": (total + limit - 1) // limit,
        "current_page": page,
    }


# ==============================
# Nearby boarding houses (Homepage view)
# ==============================
@router.get("/{university}/{student_id}/nearby", response_model=dict)
async def get_nearby_boarding_houses(
    university: str,
    student_id: str,
    use_profile_location: bool = True,
    current_lat: Optional[float] = None,
    current_lon: Optional[float] = None,
    use_region_anchor: bool = Query(True, description="Snap/fine-tune origin via regional anchor if available"),
    region: Optional[str] = Query(None, description="Optional region name (defaults to the student's university)"),
    max_radius_m: int = Query(2000, ge=50, le=5000),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=24),
    current_user: dict = Depends(get_premium_student_or_admin),
):
    """
    Return nearby boarding houses within a given radius.
    - Origin can be taken from the student's profile or provided coordinates.
    - Optional regional anchor recalculation for consistent routing contexts.
    """
    # ✅ Identity check
    if current_user.get("role") == "student" and student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    # ✅ Resolve origin location
    if use_profile_location:
        student_doc = (
            db.collection("USERS")
            .document(university)
            .collection("students")
            .document(student_id)
            .get()
        )
        if not student_doc.exists:
            raise HTTPException(status_code=404, detail="Student not found")
        sdata = student_doc.to_dict()
        origin_lat, origin_lon = sdata.get("lat"), sdata.get("lon")
        if origin_lat is None or origin_lon is None:
            raise HTTPException(status_code=404, detail="No stored location. Please update your location.")
    else:
        if current_lat is None or current_lon is None:
            raise HTTPException(
                status_code=400,
                detail="current_lat and current_lon are required when use_profile_location=False",
            )
        origin_lat, origin_lon = current_lat, current_lon

    # ✅ Optionally adjust origin via region anchor (snap or fine-tune)
    adjusted_lat, adjusted_lon = origin_lat, origin_lon
    effective_region = (region or university)
    if use_region_anchor:
        adjusted_lat, adjusted_lon = recalculate_origin(origin_lat, origin_lon, effective_region)

        # ✅ Audit: store last origin and adjusted origin
        db.collection("USERS").document(university).collection("students").document(student_id).update(
            {
                "last_origin": [origin_lat, origin_lon],
                "adjusted_origin": [adjusted_lat, adjusted_lon],
                "origin_recalculated_at": firestore.SERVER_TIMESTAMP,
                "origin_region": effective_region,
            }
        )

    # ✅ Expand to cluster
    cluster_unis = CLUSTERS.get(university, [university])

    try:
        houses: List[dict] = []

        # ------------------------------
        # Global collection (BOARDINGHOUSES)
        # ------------------------------
        global_docs = (
            db.collection("BOARDINGHOUSES")
            .where("universities", "array_contains_any", cluster_unis)
            .get()
        )
        for doc in global_docs:
            data = doc.to_dict()
            gps = data.get("GPS_coordinates")
            if not gps or len(gps) != 2:
                continue

            dest_lat, dest_lon = gps
            distance = haversine(adjusted_lat, adjusted_lon, dest_lat, dest_lon)
            if distance > max_radius_m:
                continue

            houses.append(
                {
                    "id": doc.id,
                    "name_boardinghouse": data.get("name", "Unnamed"),
                    "price": data.get("price", "N/A"),
                    "image": data.get("image_1")
                    or data.get("image_2")
                    or data.get("image_3")
                    or data.get("image_4"),
                    "gender": data.get("gender", "mixed"),
                    "distance_m": round(distance, 2),
                    "location": data.get("location"),
                }
            )

        # ✅ Sort by distance
        houses_sorted = sorted(houses, key=lambda x: x["distance_m"])

        # ✅ Pagination
        total = len(houses_sorted)
        if total == 0:
            return {
                "data": [],
                "reason": "No nearby boarding houses found. Your location might be too quiet or outside known clusters.",
                "total": 0,
                "total_pages": 0,
                "current_page": page,
            }

        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated = houses_sorted[start:end]

        return {
            "data": paginated,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page,
            "origin_used": {
                "raw": [origin_lat, origin_lon],
                "adjusted": [adjusted_lat, adjusted_lon] if use_region_anchor else None,
                "region": effective_region if use_region_anchor else None,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching nearby boarding houses: {str(e)}")



# ==============================
# Boarding house full summary
# ==============================
@router.get("/{university}/{student_id}/boardinghouse/{house_id}", response_model=BoardingHouseSummary)
async def get_boardinghouse_summary(
    university: str,
    student_id: str,
    house_id: str,
    current_user: dict = Depends(get_premium_student_or_admin),
):
    """
    Return full details of a boarding house.
    Allowed: student (self) or admin (override).
    Looks in both global and scoped collections.
    """
    # ✅ Identity validation
    if current_user.get("role") == "student" and student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    # ✅ Try global collection first
    ref = db.collection("BOARDINGHOUSES").document(house_id).get()
    if not ref.exists:
        ref = (
            db.collection("HOME")
            .document(university)
            .collection("BOARDHOUSE")
            .document(house_id)
            .get()
        )

    if not ref.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = ref.to_dict()

    return BoardingHouseSummary(
        name=data.get("name", "Unnamed"),

        # Room types
        image_12=data.get("image_12"),
        price_12=data.get("price_12"),
        sharedroom_12=data.get("sharedroom_12"),

        image_6=data.get("image_6"),
        price_6=data.get("price_6"),
        sharedroom_6=data.get("sharedroom_6"),

        image_5=data.get("image_5"),
        price_5=data.get("price_5"),
        sharedroom_5=data.get("sharedroom_5"),

        image_4=data.get("image_4"),
        price_4=data.get("price_4"),
        sharedroom_4=data.get("sharedroom_4"),

        image_3=data.get("image_3"),
        price_3=data.get("price_3"),
        sharedroom_3=data.get("sharedroom_3"),

        image_2=data.get("image_2"),
        price_2=data.get("price_2"),
        sharedroom_2=data.get("sharedroom_2"),

        image_1=data.get("image_1"),
        price_1=data.get("price_1"),
        singleroom=data.get("singleroom"),

        image_apartment=data.get("image_apartment"),
        price_apartment=data.get("price_apartment"),
        apartment=data.get("apartment"),

        # Media
        gallery_images=[img for img in [
            data.get("image_1"),
            data.get("image_2"),
            data.get("image_3"),
            data.get("image_4"),
            data.get("image_5"),
            data.get("image_6"),
            data.get("image_12"),
            data.get("image_apartment"),
        ] if img],
        videos=data.get("videos", []) if isinstance(data.get("videos"), list) else [data.get("videos")] if data.get("videos") else [],
        voice_notes=data.get("voice_notes", []) if isinstance(data.get("voice_notes"), list) else [data.get("voice_notes")] if data.get("voice_notes") else [],

        # Metadata
        space_description=data.get("space_description", "Kleno will update you when number of spaces is available."),
        conditions=data.get("conditions"),
        amenities=data.get("amenities", []),
        location=data.get("location"),
        GPS_coordinates=data.get("GPS_coordinates"),
        yango_coordinates=data.get("yango_coordinates"),
    )



# ==============================
# Boarding house navigation links
# ==============================
@router.get("/{university}/{student_id}/boardinghouse/{house_id}/navigation", response_model=BoardingHouseNavigation)
async def get_boardinghouse_navigation(
    university: str,
    student_id: str,
    house_id: str,
    use_region_anchor: bool = Query(True, description="Snap/fine-tune origin via regional anchor if available"),
    region: Optional[str] = Query(None, description="Optional region name (defaults to the student's university)"),
    current_user: dict = Depends(get_premium_student_or_admin),
):
    """
    Return Google Maps and Yango navigation links for a boarding house.
    - Origin is the student's stored location (with optional regional recalculation).
    - Destination is the house GPS coordinates.
    """
    # ✅ Identity validation
    if current_user.get("role") == "student" and student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university") and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="University mismatch")

    # ✅ Resolve student origin
    student_doc = (
        db.collection("USERS")
        .document(university)
        .collection("students")
        .document(student_id)
        .get()
    )
    if not student_doc.exists:
        raise HTTPException(status_code=404, detail="Student not found")
    sdata = student_doc.to_dict()
    origin_lat, origin_lon = sdata.get("lat"), sdata.get("lon")
    if origin_lat is None or origin_lon is None:
        raise HTTPException(status_code=404, detail="No stored location. Please update your location.")

    # ✅ Resolve house destination
    ref = db.collection("BOARDINGHOUSES").document(house_id).get()
    if not ref.exists:
        ref = (
            db.collection("HOME")
            .document(university)
            .collection("BOARDHOUSE")
            .document(house_id)
            .get()
        )
    if not ref.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = ref.to_dict()
    gps = data.get("GPS_coordinates")
    yango_coords = data.get("yango_coordinates")

    if not gps or len(gps) != 2:
        raise HTTPException(status_code=400, detail="Boarding house has no valid coordinates")

    dest_lat, dest_lon = gps

    # ✅ Optional origin recalculation via regional anchor
    effective_region = (region or university)
    adj_lat, adj_lon = origin_lat, origin_lon
    if use_region_anchor:
        adj_lat, adj_lon = recalculate_origin(origin_lat, origin_lon, effective_region)

        # Audit: update student doc with last and adjusted origin
        db.collection("USERS").document(university).collection("students").document(student_id).update(
            {
                "last_origin": [origin_lat, origin_lon],
                "adjusted_origin": [adj_lat, adj_lon],
                "origin_recalculated_at": firestore.SERVER_TIMESTAMP,
                "origin_region": effective_region,
            }
        )

    # ✅ Build links
    google_link = build_google_link(adj_lat, adj_lon, dest_lat, dest_lon)
    yango_links = build_yango_links(adj_lat, adj_lon, dest_lat, dest_lon) if yango_coords else {}

    return BoardingHouseNavigation(
        google_link=google_link,
        yango_browser=yango_links.get("yango_browser"),
        yango_deep=yango_links.get("yango_deep"),
    )
