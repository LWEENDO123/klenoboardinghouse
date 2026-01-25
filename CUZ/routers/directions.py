# CUZ/routers/directions.py
from fastapi import APIRouter, Query
from typing import Optional
import math

router = APIRouter(prefix="/directions", tags=["Directions"])

# 🔹 Single regional anchor: Kalingalinga
REGION_CENTERS = {
    "kalingalinga": (-15.404706, 28.331178),
}

def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


@router.get("/google")
def get_google_directions(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    region: Optional[str] = Query(None, description="Region name (optional)"),
):
    """
    Generate a Google Maps direction link.
    If 'region' is provided and matches 'kalingalinga',
    the origin is recalculated via the regional anchor if far away (>5km).
    """

    if region and region.lower() in REGION_CENTERS:
        center_lat, center_lon = REGION_CENTERS[region.lower()]
        distance_from_center = haversine(origin_lat, origin_lon, center_lat, center_lon)

        if distance_from_center > 5:
            print(f"Routing via region center: {region} ({center_lat}, {center_lon})")
            origin_lat, origin_lon = center_lat, center_lon

    link = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_lat},{origin_lon}"
        f"&destination={dest_lat},{dest_lon}"
        f"&travelmode=driving"
    )
    return {"google_maps_url": link}


@router.get("/yango")
def get_yango_directions(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    region: Optional[str] = Query(None, description="Region name (optional)"),
):
    """
    Generate a Yango Taxi deep link.
    If 'region' is provided and matches 'kalingalinga',
    the origin is recalculated via the regional anchor if far away (>5km).
    """

    if region and region.lower() in REGION_CENTERS:
        center_lat, center_lon = REGION_CENTERS[region.lower()]
        distance_from_center = haversine(origin_lat, origin_lon, center_lat, center_lon)

        if distance_from_center > 5:
            print(f"Routing via Yango region center: {region} ({center_lat}, {center_lon})")
            origin_lat, origin_lon = center_lat, center_lon

    link = (
        f"yango://route?"
        f"start-lat={origin_lat}&start-lon={origin_lon}"
        f"&end-lat={dest_lat}&end-lon={dest_lon}"
        f"&ref=proxy_location_app"
    )
    return {"yango_url": link}
