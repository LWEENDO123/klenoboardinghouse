# Available/check_boarding.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from USERS.firebase import db  # Firestore client for database queries (assumes initialized in USERS/firebase.py)
from HOME.models import BoardingHouseHomepage  # Pydantic model for minimal/summary display, consistent with homepage
from .security import get_premium_student  # Dependency to enforce premium student access only
from datetime import datetime  # Imported for potential future use (e.g., timestamps); not currently used

router = APIRouter(prefix="/available", tags=["available"])  # Router with /available prefix; tags for Swagger docs

@router.get("/{university}", response_model=dict)  # Response is a dict like /home (for pagination metadata)
async def check_available_boarding_houses(
    university: str,  # Path param: University to scope the query (e.g., "UNZA")
    student_id: str,  # Required param: Student ID to identify and validate the requester (must match authenticated user)
    page: int = Query(1, ge=1),  # Query param: Page number for pagination (starts at 1, enforced >=1)
    limit: int = Query(10, ge=1, le=50),  # Query param: Results per page (1-50, defaults to 10 for performance)
    current_user: dict = Depends(get_premium_student)  # Dependency: Ensures role=student, premium=True, and provides user details
):
    """
    Premium-only endpoint to fetch paginated summaries of boarding houses with available spaces.
    - Requires student_id to match the authenticated user's ID for security (like an ID check at a university entrance).
    - Filters for houses where at least one room type (shared_4/3/2 or single) is "available".
    - Displays minimal details (BoardingHouseHomepage model) like the homepage view.
    - Returns format matches /home: {"data": [summaries], "total_pages": int, "current_page": int}.
    - For full details, use /home/boardinghouse/{id} after clicking a summary.
    """
    # Validate that the provided student_id matches the authenticated user's ID
    # This enforces personalization and security: only the student themselves can request their view
    authenticated_student_id = current_user.get("user_id")
    if not authenticated_student_id or student_id != authenticated_student_id:
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")

    # Optional: Validate that the university matches the user's university (from JWT/current_user)
    # This prevents cross-university access; assumes university is stored in current_user
    user_university = current_user.get("university")
    if user_university and university != user_university:
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")

    try:
        # Fetch all boarding houses for the university from Firestore
        boardinghouses_ref = db.collection("USERS").document(university).collection("boardinghouses").get()
        
        # Filter in-memory for available houses (at least one room "available")
        available_houses = []  # List to hold filtered BoardingHouseHomepage objects
        for doc in boardinghouses_ref:  # Iterate over each boarding house document
            data = doc.to_dict()  # Convert Firestore doc to dict
            availability_fields = [  # Check room availability statuses
                data.get("sharedroom_4"),
                data.get("sharedroom_3"),
                data.get("sharedroom_2"),
                data.get("singleroom")
            ]
            if "available" in availability_fields:  # If any room is available, include this house
                # Calculate lowest price ONLY among available rooms (differs from /home, which uses all rooms)
                prices = []  # List for prices of available rooms only
                if data.get("sharedroom_4") == "available":
                    prices.append(float(data.get("price_4", float("inf"))))  # Convert price to float; inf if missing
                if data.get("sharedroom_3") == "available":
                    prices.append(float(data.get("price_3", float("inf"))))
                if data.get("sharedroom_2") == "available":
                    prices.append(float(data.get("price_2", float("inf"))))
                if data.get("singleroom") == "available":
                    prices.append(float(data.get("price_1", float("inf"))))
                
                lowest_price = min(prices) if prices else "N/A"  # Min price or N/A if no valid prices
                
                # Select first non-null image as default (same as /home)
                image = (
                    data.get("image_4") or data.get("image_3") or
                    data.get("image_2") or data.get("image_1") or
                    "default_image.jpg"  # Fallback if no images
                )
                
                # Determine gender based on boolean flags (same as /home)
                gender = (
                    "both" if data.get("gender_both") else
                    "male" if data.get("gender_male") else
                    "female" if data.get("gender_female") else
                    "unknown"
                )
                
                # Create summary object (minimal details) and add to list
                available_houses.append(
                    BoardingHouseHomepage(
                        name_boardinghouse=data["name"],  # Boarding house name
                        price=str(lowest_price) if lowest_price != float("inf") else "N/A",  # String price
                        image=image,  # Default image
                        gender=gender,  # Inferred gender
                        rating=data.get("rating")  # Optional rating
                    )
                )
        
        # Pagination logic (same as /home for consistency)
        total = len(available_houses)  # Total available houses after filtering
        start = (page - 1) * limit  # Calculate slice start
        end = min(start + limit, total)  # Calculate slice end
        paginated_data = available_houses[start:end]  # Slice the list
        
        # Return dict with data and pagination info (matches /home response)
        return {
            "data": paginated_data,  # List of summaries (minimal details)
            "total_pages": (total + limit - 1) // limit,  # Calculated total pages
            "current_page": page  # Current page number
        }
    except Exception as e:  # Catch Firebase or other errors
        raise HTTPException(status_code=500, detail=f"Error checking available boarding houses: {str(e)}")