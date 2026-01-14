# CUZ/available/check_boarding.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from CUZ.USERS.firebase import db
from CUZ.HOME.models import BoardingHouseHomepage
from CUZ.core.security import get_premium_student
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
    current_user: dict = Depends(get_premium_student),
):
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

        # Query Firestore
        boardinghouses_ref = (
            db.collection("BOARDINGHOUSES")
            .where("universities", "array_contains_any", universities)
            .get()
        )

        # Fallback to scoped collection
        if not boardinghouses_ref:
            boardinghouses_ref = (
                db.collection("HOME")
                .document(uni)
                .collection("boardinghouse")
                .get()
            )

        available_data = []
        for doc in boardinghouses_ref:
            data = doc.to_dict()

            # Only include if any room/apartment is available
            availability_fields = [
                "sharedroom_12", "sharedroom_6", "sharedroom_5",
                "sharedroom_4", "sharedroom_3", "sharedroom_2",
                "singleroom", "apartment"
            ]
            if not any(data.get(field) == "available" for field in availability_fields):
                continue

            # Compute lowest price
            def parse_price(val):
                try:
                    if val is None:
                        return float("inf")
                    if isinstance(val, (int, float)):
                        return float(val)
                    return float(str(val).replace(",", "").replace("$", "").strip())
                except:
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

            # Pick best available image
            image = (
                data.get("image_12")
                or data.get("image_6")
                or data.get("image_5")
                or data.get("image_4")
                or data.get("image_3")
                or data.get("image_2")
                or data.get("image_1")
                or data.get("image_apartment")
            )

            if not image:
                gallery = data.get("images", [])
                if isinstance(gallery, list) and gallery:
                    image = gallery[0]

            if not image:
                image = "https://via.placeholder.com/400x200"

            # Resolve gender
            gender = (
                "mixed" if data.get("gender_both")
                else "male" if data.get("gender_male")
                else "female" if data.get("gender_female")
                else "both"
            )

            available_data.append(
                BoardingHouseHomepage(
                    id=doc.id,
                    name_boardinghouse=data.get("name", "Unnamed"),
                    price=price_str,
                    image=image,
                    gender=gender,
                    location=data.get("location", ""),
                    rating=data.get("rating"),
                    type=data.get("type", "boardinghouse"),
                    teaser_video=data.get("teaser_video") or data.get("video"),
                )
            )

        # Pagination
        total = len(available_data)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated = available_data[start:end]

        return {
            "data": paginated,
            "total": total,
            "current_page": page,
            "total_pages": (total + limit - 1) // limit,
            "has_more": end < total,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching available: {str(e)}")

