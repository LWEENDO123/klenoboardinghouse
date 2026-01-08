# Store/store.py
import random
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional

from CUZ.core.firebase import db
from CUZ.Store.models import Store
from CUZ.core.security import get_premium_student, get_current_admin
from CUZ.core.config import CLUSTERS
from CUZ.routers.region_router import recalculate_origin






router = APIRouter(prefix="/store", tags=["store"])

# ==============================
# HELPER: Generate Store ID
# ==============================
def generate_store_id(username: str) -> str:
    """Generate store_id = first letter of username + 9 random digits. Example: A123456789"""
    prefix = username[0].upper() if username else "S"
    digits = "".join([str(random.randint(0, 9)) for _ in range(9)])
    return prefix + digits

# ==============================
# ADMIN: ADD STORE
# ==============================
@router.post("/admin/{university}")
async def add_store(
    university: str,
    store: Store,
    current_user: dict = Depends(get_current_admin)
):
    """
    Admin-only endpoint to add a store to Store/{university}/stores/{store_id}.
    """
    try:
        username = current_user.get("email", "store")
        store_id = generate_store_id(username)
        store_ref = db.collection("Store").document(university).collection("stores").document(store_id)

        store_data = store.dict(exclude={"id"})  # exclude id, Firestore doc ID is separate
        store_data["university"] = university
        store_data["created_by"] = current_user.get("user_id")

        store_ref.set(store_data)

        return {
            "message": "✅ Store added successfully",
            "id": store_id,
            "data": {**store_data, "id": store_id}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding store: {str(e)}")

# ==============================
# STUDENT: GET STORES (Paginated)
# ==============================
@router.get("/{university}", response_model=dict)
async def get_stores(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_premium_student)
):
    """
    Fetch paginated stores near the university (premium students only).
    - Returns only summary info (id, name, type, details, image_url).
    - Google/Yango coordinates are NOT included here; 
      frontend will use store_id to request directions separately.
    """
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")

    try:
        stores_ref = db.collection("Store").document(university).collection("stores").get()
        stores = []
        for doc in stores_ref:
            data = doc.to_dict()
            # ✅ Only return summary fields
            store_summary = {
                "id": doc.id,
                "name": data["name"],
                "type": data["type"],
                "details": data["details"],
                "image_url": data.get("image_url"),
                "university": data["university"],
                "created_by": data["created_by"]
            }
            stores.append(store_summary)

        total = len(stores)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated_data = stores[start:end]

        return {
            "data": paginated_data,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stores: {str(e)}")


# ==============================
# STUDENT: GET GOOGLE DIRECTIONS
# ==============================
@router.get("/{university}/{store_id}/directions/google")
async def get_google_directions(
    university: str,
    store_id: str,
    student_id: str,
    current_lat: float = Query(...),
    current_lon: float = Query(...),
    region: Optional[str] = Query(None, description="Optional region hub for recalculation"),
    current_user: dict = Depends(get_premium_student)
):
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")
    try:
        doc = db.collection("Store").document(university).collection("stores").document(store_id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Store not found")
        data = doc.to_dict()
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating Google directions: {str(e)}")


# ==============================
# STUDENT: GET YANGO DIRECTIONS
# ==============================
@router.get("/{university}/{store_id}/directions/yango")
async def get_yango_directions(
    university: str,
    store_id: str,
    student_id: str,
    current_lat: float = Query(...),
    current_lon: float = Query(...),
    region: Optional[str] = Query(None, description="Optional region hub for recalculation"),
    current_user: dict = Depends(get_premium_student)
):
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")
    try:
        doc = db.collection("Store").document(university).collection("stores").document(store_id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Store not found")
        data = doc.to_dict()
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating Yango directions: {str(e)}")





@router.get("/cluster/{university}", response_model=dict)
async def get_cluster_stores(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_premium_student)
):
    """
    Fetch stores for all universities in the same cluster as the given university.
    Example: UNZA cluster includes UNZA, CHRESO, UNILUS.
    """
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")

    try:
        cluster_unis = CLUSTERS.get(university, [university])
        stores = []

        for uni in cluster_unis:
            docs = db.collection("Store").document(uni).collection("stores").get()
            for doc in docs:
                data = doc.to_dict()
                store_summary = {
                    "id": doc.id,
                    "name": data["name"],
                    "type": data["type"],
                    "details": data["details"],
                    "image_url": data.get("image_url"),
                    "university": data["university"],
                    "created_by": data["created_by"]
                }
                stores.append(store_summary)

        total = len(stores)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated_data = stores[start:end]

        return {
            "data": paginated_data,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching cluster stores: {str(e)}")
