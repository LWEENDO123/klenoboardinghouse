# CUZ/available/check_boarding.py
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from CUZ.USERS.firebase import db
from CUZ.HOME.models import BoardingHouseHomepage
from CUZ.core.security import get_current_user
from CUZ.core.config import CLUSTERS

router = APIRouter(prefix="/available", tags=["available"])


@router.get("", response_model=dict)
@router.get("/", response_model=dict)
async def get_available(
    university: Optional[str] = None,
    region: Optional[str] = None,
    student_id: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    filter: str = Query("all"),
    current_user: dict = Depends(get_current_user),
):
    """
    Paginated "available" listing that mirrors the homepage summary behavior.
    - Accepts university or region (region maps to CLUSTERS).
    - Applies the same image/gender normalization and pagination logic as /home.
    - Only returns boarding houses that have at least one available room/apartment.
    """
    try:
        uni = university or current_user.get("university")

        # Determine universities to query
        if region:
            if region not in CLUSTERS:
                raise HTTPException(status_code=400, detail="Invalid region")
            universities = CLUSTERS[region]
        elif university:
            universities = [university]
        else:
            universities = [uni]

        # Primary query: global BOARDINGHOUSES
        boardinghouses_docs = (
            db.collection("BOARDINGHOUSES")
            .where("universities", "array_contains_any", universities)
            .get()
        )

        # Fallback: scoped HOME/{uni}/boardinghouse (case-insensitive handling)
        if not boardinghouses_docs:
            boardinghouses_docs = (
                db.collection("HOME").document(uni).collection("boardinghouse").get()
            )

        houses: List[dict] = []
        for doc in boardinghouses_docs or []:
            data = doc.to_dict() or {}
            data["id"] = doc.id

            # Normalize created_at
            ca = data.get("created_at")
            if hasattr(ca, "to_datetime"):  # Firestore Timestamp
                data["created_at"] = ca.to_datetime()
            elif isinstance(ca, datetime):
                data["created_at"] = ca
            else:
                data["created_at"] = datetime.utcnow()

            # Only include if any room/apartment is available
            availability_fields = [
                "sharedroom_12", "sharedroom_6", "sharedroom_5",
                "sharedroom_4", "sharedroom_3", "sharedroom_2",
                "singleroom", "apartment"
            ]
            if not any(data.get(field) == "available" for field in availability_fields):
                continue

            houses.append(data)

        # Apply filter (e.g., "new")
        if filter and filter.lower() == "new":
            houses.sort(key=lambda h: h.get("created_at", datetime.min), reverse=True)

        # Pagination
        total = len(houses)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated = houses[start:end]

        available_data: List[BoardingHouseHomepage] = []
        for data in paginated:
            # Build images list from gallery/images
            images_list: List[str] = []
            if isinstance(data.get("gallery_images"), list):
                images_list.extend([str(x) for x in data.get("gallery_images") if x])
            if isinstance(data.get("images"), list):
                images_list.extend([str(x) for x in data.get("images") if x])

            # Legacy single image fields (try many fallbacks)
            legacy_image = (
                data.get("cover_image")
                or data.get("coverImage")
                or data.get("image")
                or data.get("image_1")
                or data.get("image_2")
                or data.get("image_3")
                or data.get("image_4")
                or data.get("image_5")
                or data.get("image_6")
                or data.get("image_12")
                or data.get("image_apartment")
            )

            cover = str(legacy_image) if legacy_image else (images_list[0] if images_list else None)
            if not cover:
                cover = "https://via.placeholder.com/400x200"

            # Compute lowest price robustly
            def parse_price(val):
                try:
                    if val is None:
                        return float("inf")
                    if isinstance(val, (int, float)):
                        return float(val)
                    return float(str(val).replace(",", "").replace("$", "").strip())
                except Exception:
                    return float("inf")

            prices = [
                parse_price(data.get("price_12")),
                parse_price(data.get("price_6")),
                parse_price(data.get("price_5")),
                parse_price(data.get("price_4")),
                parse_price(data.get("price_3")),
                parse_price(data.get("price_2")),
                parse_price(data.get("price_1")),
                parse_price(data.get("price_apartment")),
            ]
            lowest_price = min([p for p in prices if p != float("inf")], default=float("inf"))
            price_str = str(int(lowest_price)) if lowest_price != float("inf") else "N/A"

            # Resolve gender
            gender = (
                "mixed" if data.get("gender_both")
                else "male" if data.get("gender_male")
                else "female" if data.get("gender_female")
                else "both"
            )

            available_data.append(
                BoardingHouseHomepage(
                    id=str(data.get("id", "")),
                    name_boardinghouse=str(data.get("name", data.get("name_boardinghouse", "Unnamed"))),
                    price=price_str,
                    image=cover,
                    gender=gender,
                    location=str(data.get("location", "") or ""),
                    rating=(data.get("rating") if isinstance(data.get("rating"), (int, float)) else None),
                    type=str(data.get("type", "boardinghouse")),
                    teaser_video=str(data.get("teaser_video") or data.get("video") or "") if (data.get("teaser_video") or data.get("video")) else None,
                )
            )

        return {
            "data": [item.dict() for item in available_data],
            "total": total,
            "current_page": page,
            "total_pages": (total + limit - 1) // limit,
            "has_more": end < total,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching available: {str(e)}")
