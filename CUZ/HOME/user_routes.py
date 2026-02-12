# CUZ/HOME/user_routes.py
import logging
import math
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Query, Depends, HTTPException
from CUZ.yearbook.profile.storage import s3_client, RAILWAY_BUCKET 





from CUZ.USERS.firebase import db
from CUZ.HOME.models import BoardingHouseHomepage, BoardingHouseSummary
from CUZ.HOME.security import get_current_user, get_premium_student
from CUZ.USERS.security import get_admin_or_landlord
from CUZ.routers.region_router import get_boardinghouse_coords, resolve_region_offset
from CUZ.utils.token_utils import generate_location_token, decode_location_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/home", tags=["HOME"])

# Example region dictionary (keep or import your real REGIONS)
REGIONS = {
    "lusaka_west": ["UNZAM", "CUZM"],
    # add other regions as needed
}



logger = logging.getLogger("bucket_inspect")

def list_admin_bucket_contents():
    try:
        prefix = "ALL/adminL-id/"
        resp = s3_client.list_objects_v2(Bucket=RAILWAY_BUCKET, Prefix=prefix)
        contents = resp.get("Contents", [])
        if not contents:
            logger.warning(f"No objects found under prefix {prefix}")
            return []

        keys = [obj["Key"] for obj in contents]
        logger.info(f"Found {len(keys)} objects under {prefix}")
        for k in keys:
            print(k)
        return keys
    except Exception as e:
        logger.exception(f"Error listing bucket contents: {e}")
        return []



# -------------------------
# Helper: Normalize Firestore media URLs
def normalize_media_url(url: str) -> str:
    """
    Normalize Firestore-stored media URLs into clean /media/{key} paths.
    """
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        if "/media/" in url:
            url = url.split("/media/", 1)[1]
    return f"/media/{url}" if not url.startswith("/media/") else url


# -------------------------
# Shared helper: normalize documents and build homepage response
def normalize_and_build_response(boardinghouses_docs, page: int, limit: int, filter: str):
    houses = []
    for doc in boardinghouses_docs or []:
        try:
            raw = doc.to_dict() or {}
        except Exception:
            logger.exception("Failed to parse Firestore doc id=%s", getattr(doc, "id", "<unknown>"))
            continue

        doc_id = getattr(doc, "id", raw.get("id", ""))

        safe = {
            "id": str(doc_id),
            "name": raw.get("name") or raw.get("name_boardinghouse") or "Unnamed",
            # ✅ Normalize media fields
            "cover_image": normalize_media_url(raw.get("cover_image") or raw.get("image")),
            "gallery_images": [normalize_media_url(x) for x in (raw.get("gallery_images") or raw.get("images") or [])],
            "location": raw.get("location") or "",
            "rating": raw.get("rating") if isinstance(raw.get("rating"), (int, float)) else None,
            "type": raw.get("type") or "boardinghouse",
            "gender_male": bool(raw.get("gender_male")),
            "gender_female": bool(raw.get("gender_female")),
            "gender_both": bool(raw.get("gender_both")),
            "teaser_video": normalize_media_url(raw.get("teaser_video") or raw.get("video")),
        }
        houses.append(safe)

    # ... keep the rest of your pagination and homepage shaping logic unchanged ...


# ---------------------------
# Helper: Validate student identity
def validate_student_identity(university: str, student_id: str, requester_uni: Optional[str] = None, allow_cross_university: bool = False) -> bool:
    """
    Ensure the student exists in USERS/{university}/students/{student_id}.

    Parameters
    - university: the target university to check (e.g., selected from dropdown)
    - student_id: the student's id to validate
    - requester_uni: the authenticated user's university (used when allow_cross_university=True)
    - allow_cross_university: if True, validate the student_id against requester_uni instead of `university`

    Behavior
    - If allow_cross_university is False (default), validate student_id under `university`.
    - If allow_cross_university is True, validate student_id under `requester_uni`. If requester_uni is None, raises 400.
    """
    # Decide which university to validate against
    target_uni = university
    if allow_cross_university:
        if not requester_uni:
            logger.error("allow_cross_university=True but requester_uni is missing")
            raise HTTPException(status_code=400, detail="Requester university required for cross-university validation")
        target_uni = requester_uni

    if not target_uni:
        logger.error("validate_student_identity called with empty university (student_id=%s)", student_id)
        raise HTTPException(status_code=400, detail="University is required")

    logger.debug("Validating student identity student_id=%s against university=%s (allow_cross=%s requester_uni=%s)",
                 student_id, target_uni, allow_cross_university, requester_uni)

    try:
        user_ref = db.collection("USERS").document(target_uni).collection("students").document(student_id)
        snap = user_ref.get()
    except Exception:
        logger.exception("Firestore error checking student identity uni=%s student_id=%s", target_uni, student_id)
        raise HTTPException(status_code=500, detail="Error validating student identity")

    if not snap.exists:
        logger.debug("Student not found: USERS/%s/students/%s", target_uni, student_id)
        raise HTTPException(status_code=403, detail="Invalid student identity")

    logger.debug("Student validated: USERS/%s/students/%s exists", target_uni, student_id)
    return True



# Replace the existing handlers with this code in CUZ/HOME/user_routes.py

# -------------------------
# Default homepage (no scoped behavior)
@router.get("", response_model=dict)
@router.get("/", response_model=dict)
async def get_home(
    university: Optional[str] = None,
    region: Optional[str] = None,
    student_id: str = Query(...),
    scope: Optional[str] = Query(None, description="Use 'scoped' when selecting a university from the dropdown"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    filter: str = Query("all"),
    current_user: dict = Depends(get_current_user),
):
    logger.debug(
        "get_home called: university=%s region=%s scope=%s student_id=%s page=%d limit=%d filter=%s",
        university, region, scope, student_id, page, limit, filter
    )
    try:
        # Decide which university will be used for querying
        uni = university or current_user.get("university")

        # Validation: if client explicitly requested scoped browsing, validate the requester
        # against their own university (allow browsing other universities).
        try:
            if scope and scope.lower() == "scoped":
                requester_uni = current_user.get("university")
                logger.debug("Scope=scoped: validating student_id=%s against requester_uni=%s", student_id, requester_uni)
                validate_student_identity(requester_uni, student_id)
            else:
                logger.debug("Default scope: validating student_id=%s against uni=%s", student_id, uni)
                validate_student_identity(uni, student_id)
        except HTTPException:
            raise
        except Exception:
            logger.exception("validate_student_identity unexpected error for uni=%s student_id=%s", uni, student_id)
            raise HTTPException(status_code=500, detail="Error validating student identity")

        # Determine universities for broad/global queries
        if region:
            logger.debug("Region provided: %s", region)
            if region not in REGIONS:
                raise HTTPException(status_code=400, detail="Invalid region")
            universities = REGIONS[region]
        elif university:
            universities = [university]
        else:
            universities = [uni]
        logger.debug("Universities to query: %s", universities)

        # Run global query safely (array_contains_any) or fallback to scoped HOME
        boardinghouses_docs = []
        if universities:
            if len(universities) > 10:
                raise HTTPException(status_code=400, detail="Too many universities in query; reduce to 10 or fewer")
            try:
                logger.debug("Querying BOARDINGHOUSES with universities=%s", universities)
                boardinghouses_docs = safe_array_contains_any(db.collection("BOARDINGHOUSES"), "universities", universities)
                logger.debug("Global query returned %d docs", len(boardinghouses_docs) if boardinghouses_docs is not None else 0)
            except HTTPException:
                raise
            except Exception:
                logger.exception("Global BOARDINGHOUSES query failed for universities=%s", universities)
                raise HTTPException(status_code=500, detail="Error querying boardinghouses")

        # Fallback: scoped HOME/{uni}/BOARDHOUSE
        if not boardinghouses_docs:
            try:
                logger.debug("Falling back to HOME/%s/BOARDHOUSE (limit=100)", uni)
                boardinghouses_docs = db.collection("HOME").document(uni).collection("BOARDHOUSE").limit(100).get()
                logger.debug("Scoped fallback returned %d docs", len(boardinghouses_docs) if boardinghouses_docs is not None else 0)
            except Exception:
                logger.exception("Scoped fallback query failed for HOME/%s/BOARDHOUSE", uni)
                raise HTTPException(status_code=500, detail="Error querying scoped boardinghouses")

        # Normalize and return
        return normalize_and_build_response(boardinghouses_docs, page, limit, filter)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in get_home")
        raise HTTPException(status_code=500, detail="Error fetching homepage data")



# -------------------------
# Scoped endpoint (called by dropdown)
@router.get("/scoped", response_model=dict)
async def get_home_scoped(
    university: str = Query(..., description="University selected from dropdown"),
    student_id: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    filter: str = Query("all"),
    current_user: dict = Depends(get_current_user),
):
    logger.debug("get_home_scoped called: selected_uni=%s requester_uni=%s student_id=%s page=%d limit=%d filter=%s",
                 university, current_user.get("university"), student_id, page, limit, filter)
    try:
        # Step 1: validate requester against their own university (allow browsing other unis)
        user_uni = current_user.get("university")
        logger.debug("Validating requester student_id=%s against user_uni=%s", student_id, user_uni)
        try:
            validate_student_identity(user_uni, student_id)
        except HTTPException:
            raise
        except Exception:
            logger.exception("validate_student_identity unexpected error for uni=%s student_id=%s", user_uni, student_id)
            raise HTTPException(status_code=500, detail="Error validating student identity")

        # Step 2: ensure selected university exists (HOME doc)
        try:
            uni_ref = db.collection("HOME").document(university)
            exists = uni_ref.get().exists
            logger.debug("HOME/%s exists=%s", university, exists)
            if not exists:
                raise HTTPException(status_code=400, detail="Selected university not available")
        except HTTPException:
            raise
        except Exception:
            logger.exception("Error checking existence of HOME/%s", university)
            raise HTTPException(status_code=500, detail="Error validating selected university")

        # Step 3: check collection casing and presence
        try:
            bh_upper = db.collection("HOME").document(university).collection("BOARDHOUSE").limit(1).get()
            bh_lower = db.collection("HOME").document(university).collection("boardinghouse").limit(1).get()
            has_upper = bool(bh_upper)
            has_lower = bool(bh_lower)
            logger.debug("HOME/%s/BOARDHOUSE exists=%s; HOME/%s/boardinghouse exists=%s", university, has_upper, university, has_lower)
            collection_name = "BOARDHOUSE" if has_upper else ("boardinghouse" if has_lower else "BOARDHOUSE")
        except Exception:
            logger.exception("Error checking BOARDHOUSE collection existence for %s", university)
            raise HTTPException(status_code=500, detail="Error checking scoped collection")

        # Step 4: query the chosen scoped collection
        try:
            logger.debug("Querying HOME/%s/%s for boardinghouses", university, collection_name)
            boardinghouses_docs = db.collection("HOME").document(university).collection(collection_name).get()
            logger.debug("Scoped query returned %d docs", len(boardinghouses_docs) if boardinghouses_docs is not None else 0)
        except Exception:
            logger.exception("Firestore query failed for HOME/%s/%s", university, collection_name)
            raise HTTPException(status_code=500, detail="Error querying boardinghouses")

        # Step 5: normalize and build response
        return normalize_and_build_response(boardinghouses_docs, page, limit, filter)

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in get_home_scoped")
        raise HTTPException(status_code=500, detail="Error fetching scoped homepage data")


# -------------------------

# -------------------------
# Shared helper: safe array_contains_any
def safe_array_contains_any(collection_ref, field, values):
    logger.debug("safe_array_contains_any called with %d values: %s", len(values) if values else 0, values)
    if not values:
        logger.debug("safe_array_contains_any: empty values -> returning []")
        return []
    if len(values) > 10:
        logger.warning("safe_array_contains_any: values length > 10 -> rejecting request")
        raise HTTPException(status_code=400, detail="Too many values for array_contains_any; reduce to 10 or fewer")
    try:
        docs = collection_ref.where(field, "array_contains_any", values).get()
        logger.debug("safe_array_contains_any: returned %d docs", len(docs) if docs is not None else 0)
        return docs or []
    except Exception:
        logger.exception("Firestore array_contains_any failed for field=%s values=%s", field, values)
        raise HTTPException(status_code=500, detail="Error querying boardinghouses")


# -------------------------
# Shared helper: normalize documents and build homepage response
def normalize_and_build_response(boardinghouses_docs, page: int, limit: int, filter: str):
    """
    Normalize Firestore docs into the homepage response shape.
    Defensive: skips malformed docs, normalizes created_at, computes cover image and gender.
    """
    houses = []
    for doc in boardinghouses_docs or []:
        try:
            raw = doc.to_dict() or {}
        except Exception:
            logger.exception("Failed to parse Firestore doc id=%s", getattr(doc, "id", "<unknown>"))
            continue

        doc_id = getattr(doc, "id", raw.get("id", ""))
        ca = raw.get("created_at")
        try:
            if hasattr(ca, "to_datetime"):
                created_at = ca.to_datetime()
            elif isinstance(ca, datetime):
                created_at = ca
            else:
                created_at = datetime.utcnow()
        except Exception:
            logger.exception("created_at normalization failed for doc id=%s", doc_id)
            created_at = datetime.utcnow()

        safe = {
            "id": str(doc_id),
            "name": raw.get("name") or raw.get("name_boardinghouse") or "Unnamed",
            "cover_image": raw.get("cover_image") or raw.get("image") or None,
            "gallery_images": list(raw.get("gallery_images") or raw.get("images") or []),
            "location": raw.get("location") or "",
            "rating": raw.get("rating") if isinstance(raw.get("rating"), (int, float)) else None,
            "type": raw.get("type") or "boardinghouse",
            "created_at": created_at,
            "gender_male": bool(raw.get("gender_male")),
            "gender_female": bool(raw.get("gender_female")),
            "gender_both": bool(raw.get("gender_both")),
            "teaser_video": raw.get("teaser_video") or raw.get("video") or None,
        }
        houses.append(safe)

    # Apply filter
    if filter and filter.lower() == "new":
        houses.sort(key=lambda h: h.get("created_at", datetime.min), reverse=True)

    # Pagination
    total = len(houses)
    start = (page - 1) * limit
    end = min(start + limit, total)
    paginated = houses[start:end]

    homepage_data = []
    for data in paginated:
        images_list = [str(x) for x in (data.get("gallery_images") or []) if x]
        legacy_image = data.get("cover_image") or (images_list[0] if images_list else None)
        cover = str(legacy_image) if legacy_image else "https://via.placeholder.com/400x200"

        gender = (
            "mixed" if data.get("gender_both")
            else "male" if data.get("gender_male")
            else "female" if data.get("gender_female")
            else "both"
        )

        try:
            item_kwargs = {
                "id": str(data.get("id", "")),
                "name_boardinghouse": str(data.get("name", "Unnamed")),
                "image": cover,
                "cover_image": str(data.get("cover_image") or cover),
                "gender": gender,
                "location": str(data.get("location", "") or ""),
                "rating": (data.get("rating") if isinstance(data.get("rating"), (int, float)) else None),
                "type": str(data.get("type", "boardinghouse")),
                "teaser_video": (str(data.get("teaser_video")) if data.get("teaser_video") else None),
            }
            if "price" in BoardingHouseHomepage.__fields__:
                item_kwargs["price"] = data.get("price", None) or "N/A"
            homepage_data.append(BoardingHouseHomepage(**item_kwargs).dict())
        except Exception:
            logger.exception("Failed to build BoardingHouseHomepage for doc id=%s", data.get("id"))
            continue

    return {
        "data": homepage_data,
        "total": total,
        "current_page": page,
        "total_pages": (total + limit - 1) // limit if limit else 0,
        "has_more": end < total,
    }





# ---------------------------
# GET /home/boardinghouse/{id} (summary)
# ---------------------------
@router.get("/boardinghouse/{id}", response_model=BoardingHouseSummary)
async def get_boardinghouse_summary(
    id: str,
    university: str,
    student_id: str,
    current_user: dict = Depends(get_current_user),
):
    validate_student_identity(university, student_id)

    # Try global collection first
    ref = db.collection("BOARDINGHOUSES").document(id).get()
    if not ref.exists:
        ref = db.collection("HOME").document(university).collection("BOARDHOUSE").document(id).get()
    if not ref.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = ref.to_dict() or {}

    # --- Build normalized structured gallery ---
    gallery_items: list[dict] = []
    raw_gallery = data.get("gallery")

    if isinstance(raw_gallery, list) and raw_gallery:
        for item in raw_gallery:
            if not item:
                continue
            if isinstance(item, dict):
                media_type = str(item.get("type", "")).lower() or None
                url = item.get("url") or item.get("video") or item.get("image") or item.get("src")
                thumbnail = item.get("thumbnail_url") or item.get("thumbnail") or item.get("thumb")
                caption = item.get("caption") or item.get("title")
                if url:
                    if media_type not in ("image", "video"):
                        lower = str(url).lower()
                        media_type = "video" if lower.endswith((".mp4", ".m3u8", ".webm")) or "video" in lower else "image"
                    gallery_items.append({
                        "type": media_type,
                        "url": normalize_media_url(url),
                        "thumbnail_url": thumbnail,   # ✅ preserve full thumbnail URL
                        "caption": str(caption) if caption else None,
                    })
            else:
                url = str(item)
                lower = url.lower()
                media_type = "video" if lower.endswith((".mp4", ".m3u8", ".webm")) or "video" in lower else "image"
                gallery_items.append({
                    "type": media_type,
                    "url": normalize_media_url(url),
                    "thumbnail_url": None,
                    "caption": None
                })

    if not gallery_items:
        images = data.get("images") or []
        if isinstance(images, list):
            for img in images:
                if img:
                    gallery_items.append({"type": "image", "url": normalize_media_url(img), "thumbnail_url": None, "caption": None})
        videos = data.get("videos") or []
        if isinstance(videos, list):
            for v in videos:
                if v:
                    gallery_items.append({"type": "video", "url": normalize_media_url(v), "thumbnail_url": None, "caption": None})

    cover_image = normalize_media_url(
        data.get("cover_image")
        or data.get("coverImage")
        or data.get("image")
        or (gallery_items[0]["url"] if gallery_items else None)
    )

    payload = {
        "id": id,
        "name": data.get("name", "Unnamed"),
        # legacy room fields (normalized)
        "image_12": normalize_media_url(data.get("image_12")),
        "price_12": data.get("price_12"),
        "sharedroom_12": data.get("sharedroom_12"),
        "image_6": normalize_media_url(data.get("image_6")),
        "price_6": data.get("price_6"),
        "sharedroom_6": data.get("sharedroom_6"),
        "image_5": normalize_media_url(data.get("image_5")),
        "price_5": data.get("price_5"),
        "sharedroom_5": data.get("sharedroom_5"),
        "image_4": normalize_media_url(data.get("image_4")),
        "price_4": data.get("price_4"),
        "sharedroom_4": data.get("sharedroom_4"),
        "image_3": normalize_media_url(data.get("image_3")),
        "price_3": data.get("price_3"),
        "sharedroom_3": data.get("sharedroom_3"),
        "image_2": normalize_media_url(data.get("image_2")),
        "price_2": data.get("price_2"),
        "sharedroom_2": data.get("sharedroom_2"),
        "image_1": normalize_media_url(data.get("image_1")),
        "price_1": data.get("price_1"),
        "singleroom": data.get("singleroom"),
        "image_apartment": normalize_media_url(data.get("image_apartment")),
        "price_apartment": data.get("price_apartment"),
        "apartment": data.get("apartment"),

        # new structured fields
        "cover_image": cover_image,
        "gallery": gallery_items,

        # other fields
        "voice_notes": data.get("voice_notes", []) or [],
        "space_description": data.get("space_description") or data.get("spaceDescription") or "",
        "conditions": data.get("conditions"),
        "amenities": data.get("amenities", []) or [],
        "location": data.get("location", "") or "",
        "GPS_coordinates": data.get("GPS_coordinates"),
        "yango_coordinates": data.get("yango_coordinates"),
        "phone_number": data.get("phone_number") or data.get("phoneNumber") or None,
    }

    # ✅ Debug print before returning
    logger.info("BoardingHouseSummary payload for id=%s: %s", id, payload)

    try:
        return BoardingHouseSummary(**payload)
    except Exception as e:
        logger.exception("BoardingHouseSummary validation failed for id=%s", id)
        raise HTTPException(status_code=500, detail=f"Boarding house payload validation error: {str(e)}")

# (Other endpoints such as directions, landlord previews, redirects remain unchanged.
#  Add them below ensuring all referenced helpers and imports exist.)


# ---------------------------
# 🌍 Regional anchor dictionary (you can expand easily)
region_centers = {
    "lusaka_west": {
        "center": (-15.4098313, 28.206743),
        "NE": (-15.4061, 28.20963),
        "NW": (-15.4060, 28.2043),
        "SE": (-15.4110, 28.20907),
        "SW": (-15.4116, 28.2037),
    },
    # "chongwe": {"center": (-15.3292, 28.6820), ...}
}


# --------------------------------------------------
# ⚙️ Helper: Apply subtle drift correction per region
def resolve_region_offset(region: Optional[str], dest_lat: float, dest_lon: float):
    """
    Applies a small directional offset (in meters) based on regional center
    to correct visual drift on Google/Yango maps.
    """
    if not region or region not in region_centers:
        return dest_lat, dest_lon

    rdata = region_centers[region]
    center_lat, center_lon = rdata["center"]

    # Approx. meters per degree at this latitude
    m_per_deg_lat = 111_320
    m_per_deg_lon = 111_320 * math.cos(math.radians(center_lat))

    # Calculate distance and direction vector
    diff_lat = dest_lat - center_lat
    diff_lon = dest_lon - center_lon

    # Apply subtle correction (5–10 m depending on direction)
    correction_m = 8.0
    adj_lat = dest_lat + (correction_m / m_per_deg_lat) * (1 if diff_lat >= 0 else -1)
    adj_lon = dest_lon + (correction_m / m_per_deg_lon) * (1 if diff_lon >= 0 else -1)

    return round(adj_lat, 6), round(adj_lon, 6)


# --------------------------------------------------
# 🚕 Yango Directions Endpoint (Android-safe)
# --------------------------------------------------
@router.get("/yango/{id}")
async def get_yango_links(
    id: str,
    university: str,
    student_id: str,
    current_lat: float = Query(...),
    current_lon: float = Query(...),
    tariff: str = Query("econom"),
    lang: str = Query("en"),
    secure: bool = Query(False),
    region: Optional[str] = Query(None),
    current_user: dict = Depends(get_premium_student),
):
    validate_student_identity(university, student_id)

    # 🔹 Try region-based lookup first
    dest_lat, dest_lon = None, None
    if region:
        try:
            dest_lat, dest_lon = get_boardinghouse_coords(region, id)
        except Exception:
            pass

    # 🔹 Fallback to Firestore
    if not dest_lat or not dest_lon:
        doc = db.collection("BOARDINGHOUSES").document(id).get()
        if not doc.exists:
            doc = db.collection("HOME").document(university).collection("boardinghouse").document(id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")

        data = doc.to_dict()
        coords = data.get("yango_coordinates") or data.get("GPS_coordinates")
        if not coords or len(coords) != 2:
            raise HTTPException(status_code=400, detail="Yango coordinates missing")
        dest_lat, dest_lon = coords

    # ✅ Apply drift correction
    dest_lat, dest_lon = resolve_region_offset(region, dest_lat, dest_lon)

    # Build links
    browser_link = (
        "https://yango.com/en_int/order/"
        f"?gfrom={current_lat},{current_lon}&gto={dest_lat},{dest_lon}"
        f"&tariff={tariff}&lang={lang}"
    )
    deep_link = (
        f"yango://route?start-lat={current_lat}&start-lon={current_lon}"
        f"&end-lat={dest_lat}&end-lon={dest_lon}"
    )

    return {
        "browser_link": browser_link,
        "deep_link": deep_link,
        "pickup": [current_lat, current_lon],
        "dropoff": [dest_lat, dest_lon],
        "region": region or "direct",
        "service": "yango",
    }





# --------------------------------------------------
# 🗺️ Google Maps Directions Endpoint
@router.get("/google/{id}")
async def get_google_directions(
    id: str,
    university: str,
    student_id: str,
    current_lat: Optional[float] = Query(None),
    current_lon: Optional[float] = Query(None),
    secure: bool = Query(False),
    region: Optional[str] = Query(None),
    current_user: dict = Depends(get_premium_student),
):
    validate_student_identity(university, student_id)

    # 🔹 Try region-based lookup first
    dest_lat, dest_lon = None, None
    if region:
        try:
            dest_lat, dest_lon = get_boardinghouse_coords(region, id)
        except Exception:
            pass

    # 🔹 Fallback to Firestore GPS coordinates
    if not dest_lat or not dest_lon:
        ref = db.collection("BOARDINGHOUSES").document(id).get()
        if not ref.exists:
            ref = db.collection("HOME").document(university).collection("boardinghouse").document(id).get()
        if not ref.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")

        data = ref.to_dict()
        coords = data.get("GPS_coordinates")
        if not coords or len(coords) != 2:
            raise HTTPException(status_code=400, detail="Google coordinates not available")
        dest_lat, dest_lon = coords

    # ✅ Apply regional drift correction
    dest_lat, dest_lon = resolve_region_offset(region, dest_lat, dest_lon)

    # Build link
    if current_lat is not None and current_lon is not None:
        link = f"https://www.google.com/maps/dir/?api=1&origin={current_lat},{current_lon}&destination={dest_lat},{dest_lon}"
    else:
        link = f"https://www.google.com/maps/dir/?api=1&destination={dest_lat},{dest_lon}"

    return {
        "link": link,
        "region": region or "direct",
        "service": "google",
    }
# --------------------------------------------------


# 🔐 Redirect Endpoints (Unchanged)
@router.get("/yango/redirect/{token}")
async def redirect_to_yango(token: str):
    data = decode_location_token(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    deep_link = (
        f"yango://route?start-lat={data['start_lat']}&start-lon={data['start_lon']}"
        f"&end-lat={data['end_lat']}&end-lon={data['end_lon']}"
        f"&appmetrica_tracking_id=1178268795219780156"
    )
    return RedirectResponse(url=deep_link)


@router.get("/google/redirect/{token}")
async def redirect_to_google(token: str):
    data = decode_location_token(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if data["start_lat"] and data["start_lon"]:
        link = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={data['start_lat']},{data['start_lon']}"
            f"&destination={data['end_lat']},{data['end_lon']}"
        )
    else:
        link = f"https://www.google.com/maps/dir/?api=1&destination={data['end_lat']},{data['end_lon']}"
    return RedirectResponse(url=link)
  
#---------------------------
# GET /home/directions/busstop/{id}
# ---------------------------
@router.get("/directions/busstop/{id}")
async def get_busstop_directions(
    id: str,
    university: str,
    student_id: str,
    current_lat: float = Query(...),
    current_lon: float = Query(...),
    current_user: dict = Depends(get_premium_student),
):
    """
    Returns Google Maps directions from student's current location to the bus stop
    defined in public_T, along with human-readable bus instructions.
    """
    # Validate student identity
    user_ref = db.collection("USERS").document(university).collection("students").document(student_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=403, detail="Invalid student identity")

    # Fetch boarding house
    ref = db.collection("BOARDINGHOUSES").document(id).get()
    if not ref.exists:
        ref = db.collection("HOME").document(university).collection("boardinghouse").document(id).get()
    if not ref.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = ref.to_dict()
    public_T = data.get("public_T")

    if not public_T:
        return {
            "message": "This boarding house is close to the university. No bus stop directions required."
        }

    coords = public_T.get("coordinates")
    instructions = public_T.get("instructions", "")

    if not coords or len(coords) != 2:
        raise HTTPException(status_code=400, detail="Bus stop coordinates missing")

    dest_lat, dest_lon = coords

    # Build Google Maps link
    link = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={current_lat},{current_lon}"
        f"&destination={dest_lat},{dest_lon}"
    )

    return {
        "bus_stop_link": link,
        "bus_stop_coordinates": coords,
        "instructions": instructions,
        "service": "google"
    }



@router.get("/boardinghouse/{id}", response_model=BoardingHouseSummary)
async def get_boardinghouse_summary(
    id: str,
    university: str,
    student_id: str,
    current_user: dict = Depends(get_current_user),
):
    try:
        validate_student_identity(university, student_id)

        # Try global collection first
        ref = db.collection("BOARDINGHOUSES").document(id).get()
        if not ref.exists:
            ref = (
                db.collection("HOME")
                .document(university)
                .collection("boardinghouse")
                .document(id)
                .get()
            )

        if not ref.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")

        data = ref.to_dict()

        # ✅ Collect all images into an album array
        images = [
            data.get("image_1"),
            data.get("image_2"),
            data.get("image_3"),
            data.get("image_4"),
            data.get("image_5"),
            data.get("image_6"),
            data.get("image_7"),
            data.get("image_8"),
            da

        ]
        images = [img for img in images if img]  # remove None values

        return {
            "id": id,
            "name": data.get("name", "Unnamed"),
            "images": images,   # ✅ new album field
            "price_1": data.get("price_1"),
            "price_2": data.get("price_2"),
            "price_3": data.get("price_3"),
            "price_4": data.get("price_4"),
            "singleroom": data.get("singleroom"),
            "sharedroom_2": data.get("sharedroom_2"),
            "sharedroom_3": data.get("sharedroom_3"),
            "sharedroom_4": data.get("sharedroom_4"),
            "amenities": data.get("amenities", []),
            "location": data.get("location", ""),
            "landlord_id": data.get("landlord_id", None),  # ✅ keep landlord reference
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching boarding house summary: {str(e)}")




@router.get("/boardinghouse/{id}/landlord-phone")
async def get_landlord_phone(
    id: str,
    university: str,
    student_id: str,
    current_user: dict = Depends(get_premium_student),  # ✅ premium-only
):
    """
    Fetch boarding house phone number directly.
    Premium students only.
    """
    try:
        # Fetch boarding house (global first, fallback to university HOME)
        ref = db.collection("BOARDINGHOUSES").document(id).get()
        if not ref.exists:
            ref = db.collection("HOME").document(university).collection("BOARDHOUSE").document(id).get()
        if not ref.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")

        data = ref.to_dict()
        phone_number = data.get("phone_number")
        if not phone_number:
            raise HTTPException(status_code=404, detail="Phone number not available for this boarding house")

        return {
            "house_id": id,
            "phone_number": phone_number,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching boarding house phone number: {str(e)}")





@router.get("", response_model=dict)
@router.get("/", response_model=dict)
async def get_home(
    university: Optional[str] = None,
    region: Optional[str] = None,
    student_id: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    filter: str = Query("all"),   # ✅ new filter param
    current_user: dict = Depends(get_current_user),
):
    try:
        # ✅ Validate student identity
        uni = university or current_user.get("university")
        validate_student_identity(uni, student_id)

        # ✅ Determine universities to query
        if region:
            if region not in REGIONS:
                raise HTTPException(status_code=400, detail="Invalid region")
            universities = REGIONS[region]
        elif university:
            universities = [university]
        else:
            universities = [current_user.get("university")]

        # ✅ Query Firestore
        boardinghouses_ref = (
            db.collection("BOARDINGHOUSES")
            .where("universities", "array_contains_any", universities)
            .get()
        )

        # ✅ Fallback to university-specific path
        if not boardinghouses_ref:
            boardinghouses_ref = (
                db.collection("HOME")
                .document(uni)
                .collection("boardinghouse")
                .get()
            )

        houses = [doc.to_dict() | {"id": doc.id} for doc in boardinghouses_ref]

        # ✅ Apply filter
        if filter == "new":
            houses.sort(
                key=lambda h: h.get("created_at"),
                reverse=True
            )

        # ✅ Pagination math
        total = len(houses)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated = houses[start:end]

        homepage_data = []
        for data in paginated:
            # Compute lowest available price
            prices = [
                float(data.get("price_4", float("inf"))),
                float(data.get("price_3", float("inf"))),
                float(data.get("price_2", float("inf"))),
                float(data.get("price_1", float("inf"))),
            ]
            lowest_price = min([p for p in prices if p != float("inf")], default=float("inf"))
            price_str = str(lowest_price) if lowest_price != float("inf") else "N/A"

            # Pick best available image
            image = (
                data.get("image_4")
                or data.get("image_3")
                or data.get("image_2")
                or data.get("image_1")
                or "default_image.jpg"
            )

            # Resolve gender
            gender = (
                "both"
                if data.get("gender_both")
                else "male"
                if data.get("gender_male")
                else "female"
                if data.get("gender_female")
                else "unknown"
            )

            homepage_data.append(
                BoardingHouseHomepage(
                    id=data["id"],
                    name_boardinghouse=data.get("name", "Unnamed"),
                    price=price_str,
                    image=image,
                    gender=gender,
                    location=data.get("location", ""),
                    rating=data.get("rating"),
                )
            )

        # ✅ Add has_more flag for infinite scroll
        has_more = end < total

        return {
            "data": homepage_data,
            "total": total,
            "current_page": page,
            "total_pages": (total + limit - 1) // limit,
            "has_more": has_more,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching homepage data: {str(e)}"
        )





# ---------------------------
# Landlord: Google preview for a boarding house
# ---------------------------
@router.get("/landlord/{house_id}/google", response_model=dict)
async def landlord_google_preview(
    house_id: str,
    university: str,
    region: Optional[str] = Query(None),
    current_user: dict = Depends(get_admin_or_landlord),
):
    """
    Landlord/admin preview of Google Maps directions for their boarding house.
    Returns a destination-only deep link, with optional regional offset applied.
    """
    if current_user.get("role") not in ["landlord", "admin"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Try global collection first, then scoped
    ref = db.collection("BOARDINGHOUSES").document(house_id).get()
    if not ref.exists:
        ref = db.collection("HOME").document(university).collection("boardinghouse").document(house_id).get()
    if not ref.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = ref.to_dict()
    coords = data.get("GPS_coordinates")
    if not coords or len(coords) != 2:
        raise HTTPException(status_code=400, detail="Google coordinates not available")

    dest_lat, dest_lon = coords
    # Optional subtle drift correction if your helper is present in this file
    try:
        dest_lat, dest_lon = resolve_region_offset(region, dest_lat, dest_lon)
    except Exception:
        pass

    link = f"https://www.google.com/maps/dir/?api=1&destination={dest_lat},{dest_lon}"

    return {
        "link": link,
        "service": "google",
        "boardinghouse_id": house_id,
        "region": region or "direct",
    }


# ---------------------------
# Landlord: Yango preview for a boarding house
# ---------------------------
@router.get("/landlord/{house_id}/yango", response_model=dict)
async def landlord_yango_preview(
    house_id: str,
    university: str,
    region: Optional[str] = Query(None),
    tariff: str = Query("econom"),
    lang: str = Query("en"),
    current_user: dict = Depends(get_admin_or_landlord),
):
    """
    Landlord/admin preview of Yango directions for their boarding house.
    Returns both browser and deep links, with optional regional offset applied.
    """
    if current_user.get("role") not in ["landlord", "admin"]:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Try global collection first, then scoped
    ref = db.collection("BOARDINGHOUSES").document(house_id).get()
    if not ref.exists:
        ref = db.collection("HOME").document(university).collection("boardinghouse").document(house_id).get()
    if not ref.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = ref.to_dict()
    coords = data.get("yango_coordinates") or data.get("GPS_coordinates")
    if not coords or len(coords) != 2:
        raise HTTPException(status_code=400, detail="Yango coordinates not available")

    dest_lat, dest_lon = coords
    # Optional subtle drift correction if your helper is present in this file
    try:
        dest_lat, dest_lon = resolve_region_offset(region, dest_lat, dest_lon)
    except Exception:
        pass

    browser_link = (
        f"https://yango.com/en_int/order/"
        f"?gto={dest_lat},{dest_lon}&tariff={tariff}&lang={lang}"
    )
    deep_link = (
        f"yango://route?"
        f"end-lat={dest_lat}&end-lon={dest_lon}"
    )

    return {
        "browser_link": browser_link,
        "deep_link": deep_link,
        "service": "yango",
        "boardinghouse_id": house_id,
        "region": region or "direct",
        "tariff": tariff,
        "lang": lang,
    }
