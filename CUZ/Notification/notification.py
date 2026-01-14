# CUZ/notification/routes.py
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, Dict, Any
from datetime import datetime

from CUZ.core.firebase import db
from firebase_admin import messaging
from google.cloud import firestore
from CUZ.core.security import get_admin_or_landlord, get_student_or_admin



router = APIRouter(prefix="/notification", tags=["notification"])

# -------------------------
# -------------------------
# Helper: safe formatter
# -------------------------
class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"

def render_template(template: str, params: Dict[str, Any]) -> str:
    try:
        return template.format_map(SafeDict(params or {}))
    except Exception:
        return template

# -------------------------
# Template management (admin)
# -------------------------
@router.post("/{university}/templates", dependencies=[Depends(get_admin_or_landlord)])
async def create_template(
    university: str,
    name: str = Body(..., embed=True),
    category: str = Body(..., embed=True),
    title_template: str = Body(..., embed=True),
    body_template: str = Body(..., embed=True),
    current_user: dict = Depends(get_admin_or_landlord),
):
    if category not in ["party", "university", "boardinghouse"]:
        raise HTTPException(status_code=400, detail="Invalid category")

    try:
        templates_ref = db.collection("NOTIFICATION_TEMPLATES").document(university).collection(category)
        doc_ref = templates_ref.document()
        data = {
            "name": name,
            "title_template": title_template,
            "body_template": body_template,
            "category": category,
            "created_by": current_user.get("user_id"),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        doc_ref.set(data)
        return {"message": "Template created", "id": doc_ref.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating template: {e}")

@router.put("/{university}/templates/{category}/{template_id}", dependencies=[Depends(get_admin_or_landlord)])
async def update_template(
    university: str,
    category: str,
    template_id: str,
    name: Optional[str] = Body(None, embed=True),
    title_template: Optional[str] = Body(None, embed=True),
    body_template: Optional[str] = Body(None, embed=True),
    current_user: dict = Depends(get_admin_or_landlord),
):
    if category not in ["party", "university", "boardinghouse"]:
        raise HTTPException(status_code=400, detail="Invalid category")

    try:
        ref = db.collection("NOTIFICATION_TEMPLATES").document(university).collection(category).document(template_id)
        snapshot = ref.get()
        if not snapshot.exists:
            raise HTTPException(status_code=404, detail="Template not found")

        updates = {}
        if name is not None:
            updates["name"] = name
        if title_template is not None:
            updates["title_template"] = title_template
        if body_template is not None:
            updates["body_template"] = body_template

        if updates:
            updates["updated_at"] = datetime.utcnow()
            ref.update(updates)

        return {"message": "Template updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating template: {e}")

@router.get("/{university}/templates/{category}")
async def list_templates(
    university: str,
    category: str,
    current_user: dict = Depends(get_admin_or_landlord),
):
    if category not in ["party", "university", "boardinghouse"]:
        raise HTTPException(status_code=400, detail="Invalid category")
    try:
        docs = db.collection("NOTIFICATION_TEMPLATES").document(university).collection(category).stream()
        templates = [{**doc.to_dict(), "id": doc.id} for doc in docs]
        return {"data": templates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing templates: {e}")


# -------------------------
# Send notification (aligned with new events)
# -------------------------
@router.post("/{university}/{category}/send")
async def send_notification(
    university: str,
    category: str,
    event_id: Optional[str] = Body(None, embed=True),
    title: Optional[str] = Body(None, embed=True),
    body: Optional[str] = Body(None, embed=True),
    template_id: Optional[str] = Body(None, embed=True),
    params: Optional[Dict[str, Any]] = Body(None, embed=True),
    target_topic: Optional[str] = Body(None, embed=True),
    target_token: Optional[str] = Body(None, embed=True),
    current_user: dict = Depends(get_student_or_admin),
):
    if category not in ["party", "university", "boardinghouse"]:
        raise HTTPException(status_code=400, detail="Invalid category")

    topic = target_topic or f"{category}_{university}"

    try:
        # ✅ If event_id is provided, fetch event details
        if category == "university" and event_id:
            event_doc = db.collection("EVENT").document(university).collection("events").document(event_id).get()
            if event_doc.exists:
                event_data = event_doc.to_dict()
                title = title or f"New Event: {event_data.get('title')}"
                body = body or f"{event_data.get('title')} scheduled on {event_data.get('date')} at {event_data.get('time')}"

        # ✅ Template rendering
        if template_id:
            templ_ref = db.collection("NOTIFICATION_TEMPLATES").document(university).collection(category).document(template_id)
            templ_snap = templ_ref.get()
            if not templ_snap.exists:
                raise HTTPException(status_code=404, detail="Template not found")
            templ = templ_snap.to_dict() or {}
            title = render_template(templ.get("title_template", ""), params or {})
            body = render_template(templ.get("body_template", ""), params or {})
        else:
            if not title or not body:
                raise HTTPException(status_code=400, detail="Provide either title/body or template_id")

        payload = {"event_id": event_id or "", "template_id": template_id or ""}

        # ✅ Send via FCM
        if target_token:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                token=target_token,
                data={k: str(v) for k, v in payload.items()},
            )
        else:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                topic=topic,
                data={k: str(v) for k, v in payload.items()},
            )
        fcm_response = messaging.send(message)

        # ✅ Store in Firestore
        notif_data = {
            "title": title,
            "body": body,
            "category": category,
            "event_id": event_id,
            "template_id": template_id,
            "params": params or {},
            "target_topic": topic if not target_token else None,
            "target_token": target_token if target_token else None,
            "sent_by": current_user.get("user_id"),
            "timestamp": datetime.utcnow(),
            "read_by": [],
        }
        db.collection("USERS").document(university).collection("notifications").add(notif_data)

        return {"message": "Notification sent", "fcm_response": fcm_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")
    

# -------------------------
# Fetch notifications (with structured room updates)
# -------------------------
@router.get("/{university}")
async def get_notifications(
    university: str,
    student_id: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None, enum=["party", "university", "boardinghouse", "tracking"]),
    current_user: dict = Depends(get_student_or_admin),
):
    # ✅ Identity enforcement
    if student_id != current_user.get("user_id"):
        raise HTTPException(status_code=403, detail="Invalid student ID")
    if university != current_user.get("university"):
        raise HTTPException(status_code=403, detail="University mismatch")

    try:
        notifications_ref = db.collection("USERS").document(university).collection("notifications")
        if category:
            notifications_ref = notifications_ref.where("category", "==", category)

        docs = list(
            notifications_ref.order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
        )

        notifications = []
        for doc in docs:
            data = doc.to_dict()
            is_read = student_id in data.get("read_by", [])

            # ✅ Parse structured updates if present
            structured_updates = {}
            if "updates" in data and isinstance(data["updates"], dict):
                for field, value in data["updates"].items():
                    if field.endswith("_count") and isinstance(value, int):
                        # Example: sharedroom_12_count → {"12-shared": 2}
                        room_type = field.replace("_count", "").replace("sharedroom_", "") \
                                         .replace("singleroom", "single room") \
                                         .replace("apartment", "apartment")
                        structured_updates[room_type] = value
                    elif field in ["sharedroom_12","sharedroom_6","sharedroom_5","sharedroom_4",
                                   "sharedroom_3","sharedroom_2","singleroom","apartment"]:
                        room_type = field.replace("sharedroom_", "") \
                                         .replace("singleroom", "single room") \
                                         .replace("apartment", "apartment")
                        structured_updates[room_type] = value

            notifications.append({
                "id": doc.id,
                **data,
                "read": is_read,
                "structured_updates": structured_updates  # ✅ new field
            })

        # ✅ Pagination
        start = (page - 1) * limit
        end = min(start + limit, len(notifications))
        paginated = notifications[start:end]

        return {
            "data": paginated,
            "total": len(notifications),
            "total_pages": (len(notifications) + limit - 1) // limit,
            "current_page": page,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching notifications: {str(e)}")



# -------------------------
# Boardinghouse update notification
# -------------------------
@router.post("/{university}/boardinghouse/{house_id}/update_notify")
async def notify_boardinghouse_update(
    university: str,
    house_id: str,
    updates: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_admin_or_landlord),
):
    """
    Landlord/admin triggers a boardinghouse update notification.
    Broadcasts detailed availability (room types + counts) to premium and generic student topics.
    """
    house_ref = db.collection("BOARDINGHOUSES").document(house_id)
    house_doc = house_ref.get()
    if not house_doc.exists:
        raise HTTPException(status_code=404, detail="Boardinghouse not found")

    house = house_doc.to_dict()
    bh_name = house.get("name", "Boardinghouse")

    # ✅ Build detailed availability message
    room_msgs = []
    for field, value in updates.items():
        # Example: {"sharedroom_12_count": 2}
        if field.endswith("_count") and isinstance(value, int):
            room_type = field.replace("_count", "").replace("sharedroom_", "") \
                             .replace("singleroom", "single room") \
                             .replace("apartment", "apartment")
            room_msgs.append(f"{value} space(s) in {room_type}")
        elif field in ["sharedroom_12","sharedroom_6","sharedroom_5","sharedroom_4",
                       "sharedroom_3","sharedroom_2","singleroom","apartment"]:
            if value and value.lower() == "available":
                room_type = field.replace("sharedroom_", "") \
                                 .replace("singleroom", "single room") \
                                 .replace("apartment", "apartment")
                room_msgs.append(f"{room_type} available")

    if room_msgs:
        detailed_body = f"{bh_name} has new openings: " + ", ".join(room_msgs)
    else:
        detailed_body = f"{bh_name} has updated its listings."

    detailed_title = f"Update at {bh_name}"

    premium_topic = f"boardinghouse_{university}_premium"
    generic_topic = f"boardinghouse_{university}_generic"

    # ✅ Premium notification
    premium_msg = messaging.Message(
        notification=messaging.Notification(title=detailed_title, body=detailed_body),
        topic=premium_topic,
        data={"boardinghouse_id": house_id}
    )
    messaging.send(premium_msg)

    # ✅ Generic notification
    generic_msg = messaging.Message(
        notification=messaging.Notification(title="Boardinghouse Update", body=detailed_body),
        topic=generic_topic,
        data={"boardinghouse_id": house_id}
    )
    messaging.send(generic_msg)

    # ✅ Store in Firestore
    notif_data = {
        "title": detailed_title,
        "body": detailed_body,
        "category": "boardinghouse",
        "boardinghouse_id": house_id,
        "updates": updates,
        "timestamp": datetime.utcnow(),
        "read_by": []
    }
    db.collection("USERS").document(university).collection("notifications").add(notif_data)

    return {"message": "Boardinghouse update notifications sent", "details": room_msgs}




# -------------------------
# Upcoming event notifications (aligned with unified events)
# -------------------------
@router.post("/{university}/notify_events")
async def notify_upcoming_events(university: str, current_user: dict = Depends(get_student_or_admin)):
    try:
        docs = db.collection("EVENT").document(university).collection("events").order_by("date").get()
        events = [doc.to_dict() for doc in docs]

        now = datetime.utcnow()
        month_events = [e for e in events if datetime.fromisoformat(e["date"]).month == now.month][:5]

        notifications_sent = []
        for e in month_events:
            event_date = datetime.fromisoformat(e["date"])
            days_to_go = (event_date - now).days

            if days_to_go == 14:
                title = f"Upcoming Event: {e['title']}"
                body = f"Mark your calendars! {e['title']} is scheduled for {e['date']} at {e['time']}."
            elif days_to_go == 2:
                title = f"{e['title']} is Almost Here!"
                body = f"🎉 Only 48 hours to go until {e['title']} begins. Get ready!"
            elif days_to_go == 0:
                title = f"Today: {e['title']}"
                body = f"🎉 The wait is over! {e['title']} is happening today at {e['time']}."
            else:
                continue

            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                topic=f"university_{university}",
                data={"event_id": e.get("event_id", "")},
            )
            messaging.send(message)

            notif_data = {
                "title": title,
                "body": body,
                "category": "university",
                "event_id": e.get("event_id"),
                "timestamp": datetime.utcnow(),
                "read_by": [],
            }
            db.collection("USERS").document(university).collection("notifications").add(notif_data)

            notifications_sent.append({"event": e["title"], "days_to_go": days_to_go})

        return {"message": "Event notifications processed", "notifications_sent": notifications_sent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error notifying events: {str(e)}")
    



# -------------------------
# Tracking arrival notification (student → landlord)
# -------------------------
@router.post("/{university}/boardinghouse/{house_id}/notify_arrival")
async def notify_student_arrival(
    university: str,
    house_id: str,
    student_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_student_or_admin),
):
    """
    Notify landlords subscribed to tracking_{house_id} that a student has arrived.
    Triggered when tracking detects arrival (distance < threshold).
    """
    try:
        # Build notification payload
        title = "Student Arrival"
        body = f"Student {student_id} has arrived at boarding house {house_id}"

        # ✅ Send via FCM to landlords channel
        topic = f"tracking_{house_id}"
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            topic=topic,
            data={"student_id": student_id, "boardinghouse_id": house_id},
        )
        fcm_response = messaging.send(message)

        # ✅ Store in Firestore for auditing
        notif_data = {
            "title": title,
            "body": body,
            "category": "tracking",
            "boardinghouse_id": house_id,
            "student_id": student_id,
            "timestamp": datetime.utcnow(),
            "read_by": [],
        }
        db.collection("USERS").document(university).collection("notifications").add(notif_data)

        return {"message": "Arrival notification sent", "fcm_response": fcm_response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending arrival notification: {str(e)}")
