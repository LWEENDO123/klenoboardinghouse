# PINNED/pinned.py
from fastapi import APIRouter, Depends, HTTPException
from CUZ.core.firebase import db
from firebase_admin import messaging, firestore
from CUZ.core.security import get_premium_student

router = APIRouter(prefix="/pinned", tags=["pinned"])

@router.post("/{university}/{boardinghouse_id}")
async def pin_boarding_house(
    university: str,
    boardinghouse_id: str,
    student_id: str,
    device_token: str,
    current_user: dict = Depends(get_premium_student)
):
    # Validate student identity
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")

    try:
        # ✅ Check global or university-specific collections
        bh_ref = db.collection("BOARDINGHOUSES").document(boardinghouse_id).get()
        if not bh_ref.exists:
            bh_ref = (
                db.collection("HOME")
                .document(university)
                .collection("boardinghouse")
                .document(boardinghouse_id)
                .get()
            )
        if not bh_ref.exists:
            raise HTTPException(status_code=404, detail="Boarding house not found")

        # ✅ Ensure student exists
        student_ref = (
            db.collection("USERS")
            .document(university)
            .collection("students")
            .document(student_id)
        )
        if not student_ref.get().exists:
            raise HTTPException(status_code=404, detail="Student not found")

        # ✅ Add to pinned list
        student_ref.update({
            "pinned_boarding_houses": firestore.ArrayUnion([boardinghouse_id])
        })

        # ✅ Subscribe device to topic
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
    device_token: str,
    current_user: dict = Depends(get_premium_student)
):
    # Validate student identity
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")

    try:
        # ✅ Ensure student exists
        student_ref = (
            db.collection("USERS")
            .document(university)
            .collection("students")
            .document(student_id)
        )
        if not student_ref.get().exists:
            raise HTTPException(status_code=404, detail="Student not found")

        # ✅ Remove from pinned list
        student_ref.update({
            "pinned_boarding_houses": firestore.ArrayRemove([boardinghouse_id])
        })

        # ✅ Unsubscribe device from topic
        topic = f"boardinghouse_{boardinghouse_id}"
        messaging.unsubscribe_from_topic([device_token], topic)

        return {"message": f"Boarding house {boardinghouse_id} unpinned and unsubscribed successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error unpinning boarding house: {str(e)}")
