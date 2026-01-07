from fastapi import APIRouter, Depends, HTTPException, Query
from firebase_admin import firestore
from typing import List, Optional
from datetime import datetime

from CUZ.USERS.security import require_role
from CUZ.HOME.models import BoardingHouse, BoardingHouseSummary
from CUZ.USERS.security import verify_token

router = APIRouter()
db = firestore.client()

#Get one boarding house
@router.get("/home/{university}/{student_id}/{boardinghouse_id}", response_model=BoardingHouseSummary, tags=["Home"])
async def get_single_boardinghouse(university: str, student_id: str, boardinghouse_id: str):
    university = university.strip().upper()
    doc_ref = db.collection("HOME").document(university).collection("boardinghouse").document(boardinghouse_id)

    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = doc.to_dict()
    summary = {
        "name": data["name"],
        "images": data.get("images", []),
        "price_4": data.get("price_4"),
        "price_3": data.get("price_3"),
        "price_2": data.get("price_2"),
        "price_1": data.get("price_1"),
        "sharedroom_4": data.get("sharedroom_4"),
        "sharedroom_3": data.get("sharedroom_3"),
        "sharedroom_2": data.get("sharedroom_2"),
        "singleroom": data.get("singleroom"),
        "amenities": data.get("amenities", []),
        "location": data.get("location")
    }

    return summary


# 📍 GET: Coordinates (Premium Only)
@router.get("/home/coordinates/{student_id}/{boardinghouse_id}", tags=["Home"])
async def get_coordinates(student_id: str, boardinghouse_id: str, user=Depends(verify_token)):
    # 🔐 Premium access check
    if not user.get("Premium"):
        raise HTTPException(status_code=403, detail="Premium access required")

    # 🧠 Optional: Validate that the token's user matches the student_id
    if user.get("user_id") != student_id:
        raise HTTPException(status_code=403, detail="Token mismatch: unauthorized access")

    # 🔍 Search across universities
    for university in ["CBU", "CUZ", "UNILUS"]:
        doc_ref = db.collection("HOME").document(university).collection("boardinghouse").document(boardinghouse_id)

        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return {
                "requested_by": student_id,
                "GPS_coordinates": data.get("GPS_coordinates"),
                "yango_coordinates": data.get("yango_coordinates")
            }

    raise HTTPException(status_code=404, detail="Boarding house not found")


# 🏠 POST: Add Boarding House (Admin Only)
@router.post("/home/add-boardinghouse", tags=["Home"])
async def add_boardinghouse(
    data: BoardingHouse,
    user=Depends(require_role("landlord"))
):
    # 🔑 Generate unique ID
    doc_id = f"{data.name.replace(' ', '_')}_{data.location}"

    # 🏫 Ensure university document exists
    db.collection("HOME").document(data.university).set(
        {"created_at": datetime.utcnow().isoformat()},
        merge=True
    )

    # 🏫 Scope by university
    doc_ref = (
        db.collection("HOME")
        .document(data.university)
        .collection("boardinghouse")
        .document(doc_id)
    )

    # 📝 Save document
    doc_ref.set({
        **data.dict(),
        "created_at": datetime.utcnow().isoformat()
    })

    print(f"✅ Boarding house added under {data.university}: {doc_id}")
    return {"message": "Boarding house added", "id": doc_id}



#get all boarding houses to show on homepage
@router.get("/home/{university}/{student_id}/list", tags=["Home"])
async def get_boardinghouse_list(university: str, student_id: str):
    university = university.strip().upper()
    ref = db.collection("HOME").document(university).collection("boardinghouse")
    results = ref.stream()
    print(f"Fetching boarding houses for university: {university}")
    print(f"Ref path: HOME/{university}/boardinghouse")

    listings = []
    for doc in results:
        data = doc.to_dict()
        print(f"Found doc: {doc.id}")

        # 🧠 Resolve gender from boolean flags
        gender = None
        if data.get("gender_male"):
            gender = "Male"
        elif data.get("gender_female"):
            gender = "Female"
        elif data.get("gender_both"):
            gender = "Male/Female"

        listing = {
            "name": data.get("name"),
            "images": data.get("images", []),
            "gender": gender,
            "location": data.get("location")
        }
        listings.append(listing)

    return listings




#search engine
@router.get("/home/{university}/search", tags=["Home"])
async def search_boardinghouse_by_name(university: str, name: str = Query(..., min_length=1)):
    university = university.strip().upper()
    name = name.strip().lower()

    ref = db.collection("HOME").document(university).collection("boardinghouse")

    results = ref.stream()

    matches = []
    for doc in results:
        data = doc.to_dict()
        if data.get("name", "").lower() == name:
            gender = (
                "Male" if data.get("gender_male") else
                "Female" if data.get("gender_female") else
                "Male/Female" if data.get("gender_both") else None
            )
            matches.append({
                "name": data.get("name"),
                "images": data.get("images", []),
                "location": data.get("location"),
                "gender": gender
            })

    if not matches:
        raise HTTPException(status_code=404, detail="No boarding house found with that name")

    return matches


@router.get("/home/{university}/{student_id}/available-list", tags=["Home"])
async def get_available_boardinghouses(university: str, student_id: str):
    university = university.strip().upper()
    ref = db.collection("HOME").document(university).collection("boardinghouse")
    results = ref.stream()

    listings = []
    for doc in results:
        data = doc.to_dict()

        # Check if any room type is marked as "available"
        if any([
            data.get("singleroom") == "available",
            data.get("sharedroom_2") == "available",
            data.get("sharedroom_3") == "available",
            data.get("sharedroom_4") == "available"
        ]):
            gender = (
                "Male" if data.get("gender_male") else
                "Female" if data.get("gender_female") else
                "Male/Female" if data.get("gender_both") else None
            )

            listings.append({
                "id": doc.id,
                "name": data.get("name"),
                "images": data.get("images", []),
                "gender": gender,
                "location": data.get("location")
            })

    if not listings:
        raise HTTPException(status_code=404, detail="No available boarding houses found")

    return listings
 


