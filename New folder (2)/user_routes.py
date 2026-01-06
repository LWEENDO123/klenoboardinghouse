from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from USERS.firebase import db  # Firestore client from USERS/firebase.py
from HOME.models import BoardingHouseHomepage  # Pydantic model for minimal summaries (like HOME/user_routes.py)
from .security import get_premium_student  # Local dependency for premium student check

router = APIRouter(prefix="/pinned", tags=["pinned"])  # Router with /pinned prefix; tags for Swagger docs

@router.get("/{university}", response_model=dict)  # Response matches HOME/user_routes.py format
async def get_pinned_boarding_houses(
    university: str,  # Path param: University to scope the query
    student_id: str,  # Required param: Student ID to validate requester
    page: int = Query(1, ge=1),  # Query param: Page number for pagination (starts at 1)
    limit: int = Query(10, ge=1, le=50),  # Query param: Results per page (1-50, defaults to 10)
    current_user: dict = Depends(get_premium_student)  # Dependency: Ensures role=student, premium=True
):
    """
    Premium-only endpoint to fetch paginated summaries of pinned boarding houses.
    - Retrieves pinned_boarding_houses array from student's document.
    - Returns minimal details (BoardingHouseHomepage) like HOME/user_routes.py /home.
    - Validates student_id and university match authenticated user.
    - Returns {"data": [summaries], "total_pages": int, "current_page": int}.
    """
    # Validate student_id matches authenticated user
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    
    # Validate university matches current_user
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")
    
    try:
        # Fetch student's document to get pinned IDs
        student_ref = db.collection("USERS").document(university).collection("students").document(student_id).get()
        if not student_ref.exists:
            raise HTTPException(status_code=404, detail="Student not found")
        
        data = student_ref.to_dict()
        pinned_ids = data.get("pinned_boarding_houses", [])  # Get array or empty list if not set
        
        # Fetch summaries for each pinned ID
        pinned_houses = []
        for bh_id in pinned_ids:
            bh_ref = db.collection("USERS").document(university).collection("boardinghouses").document(bh_id).get()
            if bh_ref.exists:  # Only include valid boarding houses
                bh_data = bh_ref.to_dict()
                
                # Calculate lowest price (same as HOME/user_routes.py)
                prices = [
                    float(bh_data.get("price_4", float("inf"))),
                    float(bh_data.get("price_3", float("inf"))),
                    float(bh_data.get("price_2", float("inf"))),
                    float(bh_data.get("price_1", float("inf")))
                ]
                lowest_price = min([p for p in prices if p != float("inf")])
                
                # Select first non-null image (same as HOME/user_routes.py)
                image = (
                    bh_data.get("image_4") or bh_data.get("image_3") or
                    bh_data.get("image_2") or bh_data.get("image_1") or
                    "default_image.jpg"
                )
                
                # Determine gender (same as HOME/user_routes.py)
                gender = (
                    "both" if bh_data.get("gender_both") else
                    "male" if bh_data.get("gender_male") else
                    "female" if bh_data.get("gender_female") else
                    "unknown"
                )
                
                pinned_houses.append(
                    BoardingHouseHomepage(
                        name_boardinghouse=bh_data["name"],
                        price=str(lowest_price) if lowest_price != float("inf") else "N/A",
                        image=image,
                        gender=gender,
                        rating=bh_data.get("rating")
                    )
                )
        
        # Pagination (same as HOME/user_routes.py)
        total = len(pinned_houses)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated_data = pinned_houses[start:end]
        
        # Return dict with data and pagination info
        return {
            "data": paginated_data,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching pinned boarding houses: {str(e)}")