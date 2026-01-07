from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel

# Firestore client (assuming you're using google-cloud-firestore)
from google.cloud import firestore

# Initialize Firestore
db = firestore.Client()


#Pin a Boarding House
@router.post("/pinned/{university}/{student_id}/add", tags=["Pinned"])
async def pin_boardinghouse(university: str, student_id: str, boardinghouse_id: str = Query(...)):
    university = university.strip().upper()

    user_ref = db.collection("USERS").document(university).collection("studentinfo").document(student_id)

    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = user_doc.to_dict()
    pinned = user_data.get("pinned", [])

    if boardinghouse_id in pinned:
        return {"message": "Boarding house already pinned"}

    pinned.append(boardinghouse_id)
    user_ref.update({"pinned": pinned})

    return {"message": "Boarding house pinned successfully", "pinned": pinned}


#Show Pinned Boarding Houses(Homepage Style)
@router.get("/pinned/{university}/{student_id}/list", tags=["Pinned"])
async def get_pinned_boardinghouses(university: str, student_id: str):
    university = university.strip().upper()

    user_ref = db.collection("USERS").document(university).collection("studentinfo").document(student_id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    pinned_ids = user_doc.to_dict().get("pinned", [])
    if not pinned_ids:
        return []

    listings = []
    for boardinghouse_id in pinned_ids:
        doc_ref = db.collection("HOME").document(university).collection("boardinghouse").document(boardinghouse_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
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

    return listings



#Boarding House Summary(full display)
@router.get("/home/{university}/{student_id}/{boardinghouse_id}", response_model=BoardingHouseSummary, tags=["Home"])
async def get_single_boardinghouse(university: str, student_id: str, boardinghouse_id: str):
    university = university.strip().upper()
    doc_ref = db.collection("HOME").document(university).collection("boardinghouse").document(boardinghouse_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Boarding house not found")

    data = doc.to_dict()

    return BoardingHouseSummary(
        name=data["name"],
        images=data.get("images", []),
        price_4=data.get("price_4"),
        price_3=data.get("price_3"),
        price_2=data.get("price_2"),
        price_1=data.get("price_1"),
        sharedroom_4=data.get("sharedroom_4"),
        sharedroom_3=data.get("sharedroom_3"),
        sharedroom_2=data.get("sharedroom_2"),
        singleroom=data.get("singleroom"),
        amenities=data.get("amenities", []),
        location=data.get("location")
    )






