# file: CUZ/Yearbook/profile/event_utils.py
from fastapi import HTTPException
from datetime import datetime
from CUZ.core.firebase import db

def assert_event_portal_open(university: str, event_id: str) -> None:
    event_doc = db.collection("EVENT").document(university).collection("events").document(event_id).get()
    if not event_doc.exists:
        raise HTTPException(status_code=404, detail="Event not found")
    event_data = event_doc.to_dict()
    if not event_data.get("portal_open", True):
        raise HTTPException(status_code=403, detail="Event portal is closed")

def today_event_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d")
