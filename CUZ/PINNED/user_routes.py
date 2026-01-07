# PINNED/user_routes.py
from fastapi import APIRouter, Depends, HTTPException, Query

from CUZ.USERS.firebase import db
from CUZ.HOME.models import BoardingHouseHomepage
from CUZ.core.security import get_premium_student
# ✅ use the unified version

router = APIRouter(prefix="/pinned", tags=["pinned"])

@router.get("/{university}", response_model=dict)
async def get_pinned_boarding_houses(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_premium_student)
):
    """
    Premium-only endpoint to fetch paginated summaries of pinned boarding houses.
    - Retrieves pinned_boarding_houses array from student's document.
    - Returns minimal details (BoardingHouseHomepage).
    - Validates student_id and university match authenticated user.
    """

    # ✅ Validate student identity
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")

    try:
        # ✅ Fetch student's pinned IDs
        student_ref = (
            db.collection("USERS")
            .document(university)
            .collection("students")
            .document(student_id)
            .get()
        )
        if not student_ref.exists:
            raise HTTPException(status_code=404, detail="Student not found")

        data = student_ref.to_dict()
        pinned_ids = data.get("pinned_boarding_houses", [])

        pinned_houses = []
        for bh_id in pinned_ids:
            # ✅ Look up boarding house in global or university collection
            bh_ref = db.collection("BOARDINGHOUSES").document(bh_id).get()
            if not bh_ref.exists:
                bh_ref = (
                    db.collection("HOME")
                    .document(university)
                    .collection("boardinghouse")
                    .document(bh_id)
                    .get()
                )
            if not bh_ref.exists:
                continue  # skip invalid IDs

            bh_data = bh_ref.to_dict()

            # ✅ Calculate lowest price
            prices = [
                float(bh_data.get("price_4", float("inf"))),
                float(bh_data.get("price_3", float("inf"))),
                float(bh_data.get("price_2", float("inf"))),
                float(bh_data.get("price_1", float("inf")))
            ]
            lowest_price = min([p for p in prices if p != float("inf")], default=float("inf"))
            price_str = str(lowest_price) if lowest_price != float("inf") else "N/A"

            # ✅ Select first available image
            image = (
                bh_data.get("image_4")
                or bh_data.get("image_3")
                or bh_data.get("image_2")
                or bh_data.get("image_1")
                or "default_image.jpg"
            )

            # ✅ Normalize gender (use "mixed" instead of "both")
            gender = (
                "mixed" if bh_data.get("gender_both")
                else "male" if bh_data.get("gender_male")
                else "female" if bh_data.get("gender_female")
                else "unknown"
            )

            pinned_houses.append(
                BoardingHouseHomepage(
                    id=bh_id,
                    name_boardinghouse=bh_data.get("name", "Unnamed"),
                    price=price_str,
                    image=image,
                    gender=gender,
                    location=bh_data.get("location", ""),
                    rating=bh_data.get("rating"),
                )
            )

        # ✅ Pagination
        total = len(pinned_houses)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated_data = pinned_houses[start:end]

        return {
            "data": paginated_data,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pinned boarding houses: {str(e)}")
