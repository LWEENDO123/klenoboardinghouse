from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    AnyUrl,
    constr,
    field_validator,
    ConfigDict,
    ValidationInfo,
)
from typing import Optional, List
from CUZ.utils.sanitize import SanitizedModel
from CUZ.core.security import is_safe_url
from datetime import datetime
import random
import string


# ---------------------------
# Base Model Config
# ---------------------------
class StrictSanitizedModel(SanitizedModel):
    model_config = ConfigDict(extra="forbid")  # 🚫 forbid unexpected fields


# ---------------------------
# AUTH & SIGNUP MODELS
# ---------------------------
class StudentSignup(StrictSanitizedModel):
    first_name: constr(min_length=2, max_length=15, pattern=r"^[A-Za-z ]+$")
    last_name: constr(min_length=2, max_length=15, pattern=r"^[A-Za-z ]+$")
    email: EmailStr
    password: constr(min_length=8, max_length=64)
    phone_number: constr(min_length=7, max_length=15, pattern=r"^[0-9]+$")
    university: constr(min_length=2, max_length=50)
    pinned: Optional[constr(max_length=50)] = None
    referral_code: Optional[constr(max_length=20)] = None
    role: str = "student"
    premium: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("university", mode="before")
    def sanitize_university(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("phone_number")
    def validate_phone(cls, v: str) -> str:
        if v in {"0000000", "1111111"}:
            raise ValueError("Invalid phone number")
        return v

    @field_validator("last_name")
    def validate_name_length(cls, v: str, info: ValidationInfo) -> str:
        first = info.data.get("first_name", "")
        if len((first or "").strip() + (v or "").strip()) > 25:
            raise ValueError("Combined name length must not exceed 25 characters")
        if (first or "").strip().lower() == (v or "").strip().lower():
            raise ValueError("First and last name cannot be identical")
        return v


class LandlordSignup(StrictSanitizedModel):
    first_name: constr(min_length=2, max_length=15, pattern=r"^[A-Za-z ]+$")
    last_name: constr(min_length=2, max_length=15, pattern=r"^[A-Za-z ]+$")
    boarding_house: constr(min_length=2, max_length=100)
    email: EmailStr
    password: constr(min_length=8, max_length=64)
    phone_number: constr(min_length=7, max_length=15, pattern=r"^[0-9]+$")
    pinned: Optional[constr(max_length=50)] = None
    role: str = "landlord"
    premium: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("phone_number")
    def validate_phone(cls, v: str) -> str:
        if v in {"0000000", "1111111"}:
            raise ValueError("Invalid phone number")
        return v

    @field_validator("last_name")
    def validate_name_length(cls, v: str, info: ValidationInfo) -> str:
        first = info.data.get("first_name", "")
        if len((first or "").strip() + (v or "").strip()) > 25:
            raise ValueError("Combined name length must not exceed 25 characters")
        if (first or "").strip().lower() == (v or "").strip().lower():
            raise ValueError("First and last name cannot be identical")
        return v


class LoginInput(StrictSanitizedModel):
    email: EmailStr
    password: str
    university: Optional[str] = None

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("university", mode="before")
    def sanitize_university(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v else v


# ---------------------------
# BOARDING HOUSE MODELS
# ---------------------------
class BoardingHouseHomepage(StrictSanitizedModel):
    id: Optional[str] = None
    name_boardinghouse: constr(min_length=2, max_length=100)
    price: constr(pattern=r"^\d+(\.\d{1,2})?$")
    image: AnyUrl
    gender: constr(pattern=r"^(male|female|mixed)$")
    rating: Optional[float] = Field(None, ge=0, le=5)


class BoardingHouseSummary(StrictSanitizedModel):
    id: Optional[str] = None
    name: constr(min_length=2, max_length=100)
    amenities: List[constr(max_length=50)] = Field(default_factory=list, max_length=20)
    location: Optional[constr(max_length=200)] = None
    GPS_coordinates: Optional[List[float]] = Field(None, min_length=2, max_length=2)
    yango_coordinates: Optional[List[float]] = Field(None, min_length=2, max_length=2)
    rating: Optional[float] = Field(None, ge=0, le=5)

    image_1: Optional[AnyUrl] = None
    price_1: Optional[float] = Field(None, ge=0)
    image_2: Optional[AnyUrl] = None
    price_2: Optional[float] = Field(None, ge=0)
    image_3: Optional[AnyUrl] = None
    price_3: Optional[float] = Field(None, ge=0)
    image_4: Optional[AnyUrl] = None
    price_4: Optional[float] = Field(None, ge=0)

    @field_validator("amenities", mode="before")
    def strip_amenities(cls, v):
        if isinstance(v, list):
            return [item.strip() for item in v if isinstance(item, str)]
        return v


class BoardingHouseNavigation(StrictSanitizedModel):
    google_link: Optional[AnyUrl] = None
    yango_browser: Optional[AnyUrl] = None
    yango_deep: Optional[AnyUrl] = None

    @field_validator("*", mode="before")
    def validate_urls(cls, v):
        if v and not is_safe_url(v):
            raise ValueError("Unsafe or untrusted URL")
        return v


# ---------------------------
# YEARBOOK MODELS
# ---------------------------
class YearbookQandA(BaseModel):
    question: constr(min_length=3, max_length=100)
    answer: constr(min_length=1, max_length=300)
    model_config = ConfigDict(extra="forbid")


class YearbookEntry(BaseModel):
    semester: int = Field(..., ge=1, le=12)
    caption: constr(min_length=1, max_length=200)
    photo_url: Optional[AnyUrl] = None
    voice_note_url: Optional[AnyUrl] = None
    video_url: Optional[AnyUrl] = None
    q_and_a: List[YearbookQandA] = Field(default_factory=list, max_length=10)

    model_config = ConfigDict(extra="forbid")

    @field_validator("photo_url", "voice_note_url", "video_url", mode="before")
    def validate_urls(cls, v):
        if v and not is_safe_url(v):
            raise ValueError("Unsafe or untrusted media URL")
        return v


class QAItem(BaseModel):
    question: constr(min_length=3, max_length=100)
    answer: constr(min_length=1, max_length=300)
    model_config = ConfigDict(extra="forbid")


class FinalSemesterEntry(BaseModel):
    id: str
    name: str
    programme: str
    semester_intake: str
    caption: constr(min_length=1, max_length=200)
    photo_url: AnyUrl
    character: List[QAItem] = Field(default_factory=list, max_length=10)

    model_config = ConfigDict(extra="forbid")


class EventCard(BaseModel):
    event_id: str
    photo_urls: List[AnyUrl]
    uploaded_at: str


class StudentDetailView(BaseModel):
    student_id: str
    name: str
    programme: str
    semester_intake: str
    events: List[EventCard]
    final_semester: Optional[FinalSemesterEntry] = None


# ---------------------------
# STUDENT UNION SIGNUP
# ---------------------------
def generate_referral_code(length: int = 10) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


class StudentUnionSignup(BaseModel):
    first_name: constr(min_length=2, max_length=15, pattern=r"^[A-Za-z ]+$")
    last_name: constr(min_length=2, max_length=15, pattern=r"^[A-Za-z ]+$")
    email: EmailStr
    password: constr(min_length=8, max_length=64)
    phone_number: constr(min_length=7, max_length=15, pattern=r"^[0-9]+$")
    university: constr(min_length=2, max_length=50)
    pinned: Optional[constr(max_length=50)] = None
    referral_code: str = Field(default_factory=generate_referral_code)
    role: str = "student_union"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("email", mode="before")
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("university", mode="before")
    def sanitize_university(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("phone_number")
    def validate_phone(cls, v: str) -> str:
        if v in {"0000000", "1111111"}:
            raise ValueError("Invalid phone number")
        return v

    @field_validator("last_name")
    def validate_name_length(cls, v: str, info: ValidationInfo) -> str:
        first = info.data.get("first_name", "")
        if len((first or "").strip() + (v or "").strip()) > 25:
            raise ValueError("Combined name length must not exceed 25 characters")
        if (first or "").strip().lower() == (v or "").strip().lower():
            raise ValueError("First and last name cannot be identical")
        return v
