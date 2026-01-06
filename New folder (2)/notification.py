from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from USERS.firebase import db  # Firestore client
from firebase_admin import messaging  # For FCM sending
from .security import get_current_student, get_admin_or_landlord

router = APIRouter(prefix="/notification", tags=["notification"])

@router.post("/{university}/{category}")
async def send_notification(
    university: str,
    category: str,
    title: str,
    body: str,
    target_topic: str = None,
    event_id: Optional[str] = None,
    boardinghouse_id: Optional[str] = None,
    detail_url: Optional[str] = None,
    image_url: Optional[str] = None,  # For event imagery
    video_url: Optional[str] = None,  # For event video
    current_user: dict = Depends(get_admin_or_landlord)
):
    """
    Send a notification via FCM and store in Firestore (admin/landlord only).
    - Supports event_id, boardinghouse_id, detail_url, image_url, video_url.
    """
    if category not in ["party", "university", "boardinghouse"]:
        raise HTTPException(status_code=400, detail="Invalid category")
    
    topic = target_topic or f"{category}_{university}"
    
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic=topic,
            data={
                "event_id": event_id,
                "boardinghouse_id": boardinghouse_id,
                "detail_url": detail_url,
                "image_url": image_url,
                "video_url": video_url
            } if any([event_id, boardinghouse_id, detail_url, image_url, video_url]) else None
        )
        response = messaging.send(message)
        
        notif_data = {
            "title": title,
            "body": body,
            "category": category,
            "event_id": event_id,
            "boardinghouse_id": boardinghouse_id,
            "detail_url": detail_url,
            "image_url": image_url,
            "video_url": video_url,
            "timestamp": datetime.utcnow(),
            "read_by": []
        }
        db.collection("USERS").document(university).collection("notifications").add(notif_data)
        
        return {"message": "Notification sent successfully", "fcm_response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")

@router.get("/{university}", response_model=dict)
async def get_notifications(
    university: str,
    student_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None, enum=["party", "university", "boardinghouse"]),
    current_user: dict = Depends(get_current_student)
):
    """
    Fetch unread notifications for the student (public for students).
    - Filters by category if provided; otherwise, returns all unread.
    """
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")
    
    try:
        notifications_ref = db.collection("USERS").document(university).collection("notifications")
        if category:
            notifications_ref = notifications_ref.where("category", "==", category)
        
        unread = [doc for doc in notifications_ref.stream() if student_id not in doc.to_dict().get("read_by", [])]
        for doc in unread:
            doc.reference.update({"read_by": firestore.ArrayUnion([student_id])})
        
        total = len(unread)
        start = (page - 1) * limit
        end = min(start + limit, total)
        paginated_data = unread[start:end]
        
        notifications = [{"id": doc.id, **doc.to_dict()} for doc in paginated_data]
        
        return {
            "data": notifications,
            "total_pages": (total + limit - 1) // limit,
            "current_page": page
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching notifications: {str(e)}")