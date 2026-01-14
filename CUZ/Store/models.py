# Store/models.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal



class Store(BaseModel):
    id: Optional[str] = None  # Firestore document ID
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal["market", "gas_station", "mini_mart", "mall"]  # enforce allowed values
    details: str = Field(..., min_length=1, max_length=500)
    image_url: Optional[str] = None
    GPS_coordinates: Optional[List[float]] = None
    yango_coordinates: Optional[List[float]] = None
    university: str
    created_by: str
