# yango_google_router.py
from fastapi import APIRouter, Query
from typing import Optional
from .region_router import recalculate_origin

router = APIRouter(prefix="/directions", tags=["Directions"])


@router.get("/google")
def google_directions(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    region: Optional[str] = Query(None, description="Optional region name"),
):
    """
    Generate Google Maps route link (auto recalculates through region if provided)
    """
    new_origin_lat, new_origin_lon = recalculate_origin(origin_lat, origin_lon, region)
    
    link = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={new_origin_lat},{new_origin_lon}"
        f"&destination={dest_lat},{dest_lon}"
        f"&travelmode=driving"
    )
    return {
        "region": region or "none",
        "adjusted_origin": [new_origin_lat, new_origin_lon],
        "google_maps_url": link
    }


@router.get("/yango")
def yango_directions(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    region: Optional[str] = Query(None, description="Optional region name"),
):
    """
    Generate Yango deep link (auto recalculates through region if provided)
    """
    new_origin_lat, new_origin_lon = recalculate_origin(origin_lat, origin_lon, region)

    link = (
        f"yango://route?"
        f"start-lat={new_origin_lat}&start-lon={new_origin_lon}"
        f"&end-lat={dest_lat}&end-lon={dest_lon}"
        f"&ref=proxy_location_app"
    )
    return {
        "region": region or "none",
        "adjusted_origin": [new_origin_lat, new_origin_lon],
        "yango_url": link
    }
