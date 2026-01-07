from pydantic import BaseModel, Field
from typing import List, Optional

class BoardingHouseSummary(BaseModel):
    name: str
    images: List[str]
    price_4: Optional[str]
    price_3: Optional[str]
    price_2: Optional[str]
    price_1: Optional[str]
    sharedroom_4: Optional[str]
    sharedroom_3: Optional[str]
    sharedroom_2: Optional[str]
    singleroom: Optional[str]
    amenities: List[str]
    location: Optional[str]

class BoardingHouse(BaseModel):
    name: str 
    location: str 
    university: str 
    landlord_id: str 
    price_4: str 
    price_3: str 
    price_2: str 
    price_1: str 
    GPS_coordinates: Optional[str] 
    yango_coordinates: Optional[str] 
    gender_male: Optional[bool] = False 
    gender_female: Optional[bool] = False 
    gender_both: Optional[bool] = False 
    sharedroom_4: str = Field(..., example="available")
    sharedroom_3: str = Field(..., example="unavailable")
    sharedroom_2: str = Field(..., example="not_supported")
    singleroom: str = Field(..., example="available")
    amenities: List[str]
    images: List[str] 
    rating: Optional[float] = None
