from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime

# ---------------------------
# Unified MediaItem model
# ---------------------------
class MediaItem(BaseModel):
    type: str  # "image" or "video"
    url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None

    class Config:
        extra = "forbid"


# ---------------------------
# Model for creating boarding houses (POST)
# ---------------------------
class BoardingHouseCreate(BaseModel):
    name: str
    university: str

    # Room images, prices, statuses
    image_12: Optional[str] = None
    price_12: Optional[str] = None
    sharedroom_12: Optional[str] = None
    image_6: Optional[str] = None
    price_6: Optional[str] = None
    sharedroom_6: Optional[str] = None
    image_5: Optional[str] = None
    price_5: Optional[str] = None
    sharedroom_5: Optional[str] = None
    image_4: Optional[str] = None
    price_4: Optional[str] = None
    sharedroom_4: Optional[str] = None
    image_3: Optional[str] = None
    price_3: Optional[str] = None
    sharedroom_3: Optional[str] = None
    image_2: Optional[str] = None
    price_2: Optional[str] = None
    sharedroom_2: Optional[str] = None
    image_1: Optional[str] = None
    price_1: Optional[str] = None
    singleroom: Optional[str] = None

    image_apartment: Optional[str] = None
    price_apartment: Optional[str] = None
    apartment: Optional[str] = None

    cover_image: Optional[str] = Field(default=None, description="Primary cover image URL for the listing")
    gallery: List[MediaItem] = Field(default_factory=list, description="List of gallery media items (images and videos)")

    voice_notes: List[str] = Field(default_factory=list)
    space_description: str = Field(default="Kleno will update you when number of spaces is available.")
    conditions: Optional[str] = Field(default=None)
    amenities: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    GPS_coordinates: Optional[List[float]] = None
    yango_coordinates: Optional[List[float]] = None
    phone_number: Optional[str] = Field(default=None)

    class Config:
        extra = "forbid"


# ---------------------------
# Model for detailed view (GET)
# ---------------------------
class BoardingHouseSummary(BaseModel):
    id: str
    name: str

    cover_image: Optional[str] = None
    gallery: List[MediaItem] = Field(default_factory=list)

    # Room prices
    price_1: Optional[str] = None
    price_2: Optional[str] = None
    price_3: Optional[str] = None
    price_4: Optional[str] = None
    price_5: Optional[str] = None
    price_6: Optional[str] = None
    price_12: Optional[str] = None
    price_apartment: Optional[str] = None

    # Room statuses
    singleroom: Optional[str] = None
    sharedroom_2: Optional[str] = None
    sharedroom_3: Optional[str] = None
    sharedroom_4: Optional[str] = None
    sharedroom_5: Optional[str] = None
    sharedroom_6: Optional[str] = None
    sharedroom_12: Optional[str] = None
    apartment: Optional[str] = None

    # Room images
    image_1: Optional[str] = None
    image_2: Optional[str] = None
    image_3: Optional[str] = None
    image_4: Optional[str] = None
    image_5: Optional[str] = None
    image_6: Optional[str] = None
    image_12: Optional[str] = None
    image_apartment: Optional[str] = None

    amenities: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    conditions: Optional[str] = None
    space_description: Optional[str] = None
    phone_number: Optional[str] = None

    # ✅ Added fields
    GPS_coordinates: Optional[List[float]] = None
    yango_coordinates: Optional[List[float]] = None
    voice_notes: List[str] = Field(default_factory=list)

    class Config:
        extra = "forbid"

# ---------------------------
# Model for homepage display
# ---------------------------
class BoardingHouseHomepage(BaseModel):
    id: str
    name_boardinghouse: str
    image: str  # legacy single image field
    cover_image: Optional[str] = None
    gender: Literal["male", "female", "mixed", "both"]
    location: Optional[str] = None
    rating: Optional[float] = None
    type: Optional[str] = None
    teaser_video: Optional[str] = None

    class Config:
        extra = "forbid"


# ---------------------------
# Model for landlord editing
# ---------------------------
class BoardingHouse(BaseModel):
    name: str
    location: str
    universities: List[str]
    landlord_id: str

    phone_number: Optional[str] = None

    # Prices
    price_12: Optional[str] = None
    price_6: Optional[str] = None
    price_5: Optional[str] = None
    price_4: Optional[str] = None
    price_3: Optional[str] = None
    price_2: Optional[str] = None
    price_1: Optional[str] = None
    price_apartment: Optional[str] = None

    # Availability
    sharedroom_12: Optional[str] = None
    sharedroom_6: Optional[str] = None
    sharedroom_5: Optional[str] = None
    sharedroom_4: Optional[str] = None
    sharedroom_3: Optional[str] = None
    sharedroom_2: Optional[str] = None
    singleroom: Optional[str] = None
    apartment: Optional[str] = None

    # Images
    image_12: Optional[str] = None
    image_6: Optional[str] = None
    image_5: Optional[str] = None
    image_4: Optional[str] = None
    image_3: Optional[str] = None
    image_2: Optional[str] = None
    image_1: Optional[str] = None
    image_apartment: Optional[str] = None

    cover_image: Optional[str] = None
    images: List[str] = Field(default_factory=list)
    videos: List[str] = Field(default_factory=list)
    voice_notes: List[str] = Field(default_factory=list)

    # ✅ Optional gallery for structured media
    gallery: Optional[List[MediaItem]] = Field(
        default=None,
        description="Structured gallery of images and videos (optional)"
    )

    GPS_coordinates: Optional[List[float]] = None
    yango_coordinates: Optional[List[float]] = None

    gender_male: Optional[bool] = False
    gender_female: Optional[bool] = False
    gender_both: Optional[bool] = False

    amenities: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    conditions: Optional[str] = None
    space_description: Optional[str] = None

    public_T: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        extra = "forbid"
