#Yearbook/profile/model.py
from pydantic import BaseModel, Field, constr, EmailStr
from typing import List, Optional, Literal
from datetime import datetime

# ---------------------------
# Student Event Photos
# ---------------------------
class EventPhotos(BaseModel):
    name: str
    programme: str
    photo_urls: List[str] = Field(..., max_items=10)


# ---------------------------
# Final Semester Entry
# ---------------------------
class QAItem(BaseModel):
    question: str
    answer: str

class FinalSemesterEntry(BaseModel):
    id: str                                # unique ID for this final entry
    name: str
    programme: str
    semester_intake: str
    character: List[QAItem] = Field(..., max_items=10)  # up to 10 Q&A pairs
    caption: Optional[str] = None
    photo_url: str

# ---------------------------
# Homepage Feed Card
# ---------------------------
class HomepageCard(BaseModel):
    student_id: str
    name: str
    programme: str
    photo_url: str   # latest event photo OR final semester photo
    likes_count: int = 0   # number of hearts
    # optional: track who liked (user_ids) if you want to prevent double-liking
    liked_by: Optional[List[str]] = None


# ---------------------------
# Student Detail View
# ---------------------------
class EventCard(BaseModel):
    event_id: str
    photo_urls: List[str]
    uploaded_at: str
    likes_count: int = 0
    liked_by: Optional[List[str]] = None


class StudentDetailView(BaseModel):
    student_id: str
    name: str
    programme: str
    semester_intake: str
    events: List[EventCard] = []           # sorted latest → oldest
    final_semester: Optional[FinalSemesterEntry] = None


  
class Event(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    date: constr(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: constr(pattern=r"^\d{2}:\d{2}$")
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    GPS_coordinates: Optional[List[float]] = Field(None, min_items=2, max_items=2)
    yango_coordinates: Optional[List[float]] = Field(None, min_items=2, max_items=2)
    created_by: str
    
    category: Literal["event", "yearbook"] = "event"   # ✅ NEW FIELD
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"extra": "forbid"}


class EventResponse(BaseModel):
    event_id: str
    title: str
    date: str
    time: str
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    GPS_coordinates: Optional[List[float]] = None
    yango_coordinates: Optional[List[float]] = None
    



class UserProfile(BaseModel):
    first_name: constr(min_length=2, max_length=15, regex=r"^[A-Za-z ]+$")
    last_name: constr(min_length=2, max_length=15, regex=r"^[A-Za-z ]+$")
    full_name: str  # ✅ new field
    email: EmailStr
    phone_number: constr(min_length=7, max_length=15, regex=r"^[0-9]+$")
    university: constr(min_length=2, max_length=50)
    premium: bool = False