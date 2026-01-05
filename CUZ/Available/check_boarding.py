# Available/check_boarding.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from USERS.firebase import db  # Firestore client
from HOME.models import BoardingHouseHomepage  # ✅ import from HOME/models.py
from core.security import get_premium_student  # Security dependency
from core.config import REGIONS
from pydantic import BaseModel

router = APIRouter(prefix="/available", tags=["available"])


# ---------------------------
# Response model
# ---------------------------
class PaginatedBoardingHouseResponse(BaseModel):
    data: List[BoardingHouseHomepage]
    total_pages: int
    current_page: int


# ---------------------------
# Endpoint
# ---------------------------
@router.get("", response_model=PaginatedBoardingHouseResponse)
@router.get("/", response_model=PaginatedBoardingHouseResponse)
async def get_available(
    university: Optional[str] = None,
    region: Optional[str] = None,
    student_id: str = Query(...),
    page: int = 1,
    limit: int = 10,
    current_user: dict = Depends(get_premium_student),
):
    try:
        uni = university or current_user.get("university")

        # Determine universities to query
        if region:
            if region not in REGIONS:
                raise HTTPException(status_code=400, detail="Invalid region")
            universities = REGIONS[region]
        elif university:
            universities = [university]
        else:
            universities = [current_user.get("university")]

        # Query global collection
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

        available_data: List[BoardingHouseHomepage] = []
        for doc in boardinghouses_ref:
            data = doc.to_dict()

            # Only include if any room is available
            if any(
                data.get(field) == "available"
                for field in ["sharedroom_4", "sharedroom_3", "sharedroom_2", "singleroom"]
            ):
                prices = []
                if data.get("sharedroom_4") == "available":
                    prices.append(float(data.get("price_4", float("inf"))))
                if data.get("sharedroom_3") == "available":
                    prices.append(float(data.get("price_3", float("inf"))))
                if data.get("sharedroom_2") == "available":
                    prices.append(float(data.get("price_2", float("inf"))))
                if data.get("singleroom") == "available":
                    prices.append(float(data.get("price_1", float("inf"))))

                lowest_price = min([p for p in prices if p != float("inf")], default=float("inf"))
                price_str = str(lowest_price) if lowest_price != float("inf") else "N/A"

                image = (
                    data.get("image_4")
                    or data.get("image_3")
                    or data.get("image_2")
                    or data.get("image_1")
                    or "default_image.jpg"
                )

                # ✅ Standardize gender to "mixed" instead of "both"
                gender = (
                    "mixed" if data.get("gender_both")
                    else "male" if data.get("gender_male")
                    else "female" if data.get("gender_female")
                    else "unknown"
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
                    )
                )

        # Pagination
        total = len(available_data)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated = available_data[start:end]

        return PaginatedBoardingHouseResponse(
            data=paginated,
            total_pages=(total + limit - 1) // limit,
            current_page=page,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching available: {str(e)}")
