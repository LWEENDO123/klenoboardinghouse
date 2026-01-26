from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime

# ---------------------------
# Model for detailed view when a boarding house is clicked
# ---------------------------
class BoardingHouseSummary(BaseModel):
    name: str

    # Room type images, prices, availability
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

    # Apartment fields
    image_apartment: Optional[str] = None
    price_apartment: Optional[str] = None
    apartment: Optional[str] = None

    # Media fields
    cover_image: Optional[str] = Field(
        default=None,
        description="Primary cover image URL for the listing"
    )
    gallery_images: List[str] = Field(default_factory=list, description="List of gallery image URLs (images only)")
    videos: List[str] = Field(default_factory=list, description="List of video URLs (optional)")
    voice_notes: List[str] = Field(default_factory=list, description="List of audio note URLs (optional)")

    # New field: space availability description
    space_description: str = Field(
        default="Kleno will update you when number of spaces is available.",
        description="Text describing the number of available spaces or a fallback message"
    )

    # Landlord conditions/standards
    conditions: Optional[str] = Field(
        default=None,
        description="Brief description of landlord’s standards and conditions"
    )

    # Other metadata
    amenities: List[str] = Field(default_factory=list)
    location: Optional[str] = None
    GPS_coordinates: Optional[List[float]] = None
    yango_coordinates: Optional[List[float]] = None

    # ✅ New field: phone number stored directly on the boarding house
    phone_number: Optional[str] = Field(
        default=None,
        description=""
    )

    class Config:
        extra = "forbid"



# ---------------------------
# Model for homepage display (sorted data with lowest price)
# ---------------------------
class BoardingHouseHomepage(BaseModel):
    id: str
    name_boardinghouse: str
    # price is intentionally optional/omitted here; use lowest price logic in service layer
    image: str  # legacy single image field (kept for compatibility)
    cover_image: Optional[str] = None  # preferred explicit cover image
    gender: Literal["male", "female", "mixed", "both"]
    location: Optional[str] = None
    rating: Optional[float] = None
    type: Optional[str] = None  # "boardinghouse" or "apartment"

    # Optional teaser video for homepage cards
    teaser_video: Optional[str] = None

    class Config:
        extra = "forbid"


# ---------------------------
# Model for adding/editing boarding houses
# ---------------------------
class BoardingHouse(BaseModel):
    name: str
    location: str
    universities: List[str]
    landlord_id: str

    # Optional contact phone number
    phone_number: Optional[str] = Field(
        default=None,
        description="Contact phone number for the boarding house"
    )

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
    sharedroom_12: Optional[str] = Field(None, example="available")
    sharedroom_6: Optional[str] = Field(None, example="available")
    sharedroom_5: Optional[str] = Field(None, example="available")
    sharedroom_4: Optional[str] = Field(None, example="available")
    sharedroom_3: Optional[str] = Field(None, example="available")
    sharedroom_2: Optional[str] = Field(None, example="available")
    singleroom: Optional[str] = Field(None, example="available")
    apartment: Optional[str] = Field(None, example="available")

    # Images per room
    image_12: Optional[str] = None
    image_6: Optional[str] = None
    image_5: Optional[str] = None
    image_4: Optional[str] = None
    image_3: Optional[str] = None
    image_2: Optional[str] = None
    image_1: Optional[str] = None
    image_apartment: Optional[str] = None

    # General gallery & media
    cover_image: Optional[str] = Field(
        default=None,
        description="Primary cover image URL for the listing"
    )
    images: List[str] = Field(default_factory=list, description="Gallery image URLs")
    videos: List[str] = Field(default_factory=list, description="Video URLs")
    voice_notes: List[str] = Field(default_factory=list, description="Audio note URLs")

    # Coordinates
    GPS_coordinates: Optional[List[float]] = None
    yango_coordinates: Optional[List[float]] = None

    # Gender restrictions
    gender_male: Optional[bool] = False
    gender_female: Optional[bool] = False
    gender_both: Optional[bool] = False

    # Amenities and rating
    amenities: List[str] = Field(default_factory=list)
    rating: Optional[float] = None

    # Landlord conditions/standards
    conditions: Optional[str] = Field(
        None,
        description="Brief description of landlord’s standards and conditions"
    )

    # Space availability description
    space_description: Optional[str] = Field(
        default="Kleno will update you on the number of space available.",
        description="Text describing the number of available spaces or a fallback message"
    )

    # Bus stop navigation / public transport info
    public_T: Optional[Dict[str, Any]] = Field(
        default=None,
        example={
            "coordinates": [-15.4167, 28.2833],
            "instructions": "Take a bus to Town, drop off at Downtown, then walk to the university."
        },
        description="Bus stop navigation info"
    )

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the boarding house was created"
    )

    class Config:
        extra = "forbid"

