from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from datetime import datetime
from USERS.firebase import db  # Firestore client
from firebase_admin import messaging  # For FCM sending
from .security import get_premium_student  # Premium student check

router = APIRouter(prefix="/proxily", tags=["proxily"])

@router.post("/alert/{university}")
async def send_alert(
    university: str,
    student_id: str,
    message: str,
    boardinghouse_id: Optional[str] = None,  # Optional: Specific boarding house for alert
    current_user: dict = Depends(get_premium_student)
):
    """
    Send an alert to all landlords in the university to update their listings (premium students only).
    - Sends FCM notification to topic 'landlords_{university}' with the student's message.
    - Stores the alert in USERS/{university}/alerts for tracking.
    - Validates student_id and university.
    """
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID: Must match authenticated user")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch: Access denied for this university")

    try:
        # Send FCM notification to landlords
        topic = f"landlords_{university}"
        fcm_message = messaging.Message(
            notification=messaging.Notification(
                title="Student Alert",
                body=message
            ),
            topic=topic,
            data={"student_id": student_id, "boardinghouse_id": boardinghouse_id}
        )
        fcm_response = messaging.send(fcm_message)
        
        # Store alert in Firestore for tracking
        alert_data = {
            "message": message,
            "student_id": student_id,
            "boardinghouse_id": boardinghouse_id,
            "university": university,
            "timestamp": datetime.utcnow()
        }
        db.collection("USERS").document(university).collection("alerts").add(alert_data)
        
        return {"message": "Alert sent successfully to landlords", "fcm_response": fcm_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending alert: {str(e)}")