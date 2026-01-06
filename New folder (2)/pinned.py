from fastapi import APIRouter, Depends, HTTPException
from USERS.firebase import db  # Firestore client
from firebase_admin import messaging  # For FCM topic subscription
from .security import get_premium_student  # Premium student check
from firebase_admin import firestore  # For ArrayUnion/ArrayRemove

router = APIRouter(prefix="/pinned", tags=["pinned"])

@router.post("/{university}/{boardinghouse_id}")
async def pin_boarding_house(
    university: str,
    boardinghouse_id: str,
    student_id: str,
    device_token: str,  # Added: FCM device token for topic subscription
    current_user: dict = Depends(get_premium_student)
):
    """
    Pin a boarding house ID and subscribe to its FCM topic (premium students only).
    - Adds boardinghouse_id to student's pinned_boarding_houses array.
    - Subscribes device_token to topic 'boardinghouse_{boardinghouse_id}'.
    """
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")
    
    try:
        # Check if boarding house exists
        bh_ref = db.collection("USERS").document(university).collection("boardinghouses").document(boardinghouse_id).get()
        if not bh_ref.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")
        
        # Reference to student's document
        student_ref = db.collection("USERS").document(university).collection("students").document(student_id)
        if not student_ref.get().exists:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Add boardinghouse_id to pinned_boarding_houses
        student_ref.update({
            "pinned_boarding_houses": firestore.ArrayUnion([boardinghouse_id])
        })
        
        # Subscribe to FCM topic
        topic = f"boardinghouse_{boardinghouse_id}"
        messaging.subscribe_to_topic([device_token], topic)
        
        return {"message": f"Boarding house {boardinghouse_id} pinned and subscribed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error pinning boarding house: {str(e)}")

@router.delete("/{university}/{boardinghouse_id}")
async def unpin_boarding_house(
    university: str,
    boardinghouse_id: str,
    student_id: str,
    device_token: str,  # Added: FCM device token for topic unsubscription
    current_user: dict = Depends(get_premium_student)
):
    """
    Unpin a boarding house ID and unsubscribe from its FCM topic (premium students only).
    - Removes boardinghouse_id from pinned_boarding_houses array.
    - Unsubscribes device_token from topic 'boardinghouse_{boardinghouse_id}'.
    """
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")
    
    try:
        # Reference to student's document
        student_ref = db.collection("USERS").document(university).collection("students").document(student_id)
        if not student_ref.get().exists:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Remove boardinghouse_id from pinned_boarding_houses
        student_ref.update({
            "pinned_boarding_houses": firestore.ArrayRemove([boardinghouse_id])
        })
        
        # Unsubscribe from FCM topic
        topic = f"boardinghouse_{boardinghouse_id}"
        messaging.unsubscribe_from_topic([device_token], topic)
        
        return {"message": f"Boarding house {boardinghouse_id} unpinned and unsubscribed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error unpinning boarding house: {str(e)}")