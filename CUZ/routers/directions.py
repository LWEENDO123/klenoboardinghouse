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
    the anchor is added as a waypoint so the route passes through it.
    """

    waypoints = ""
    if region and region.lower() in REGION_CENTERS:
        center_lat, center_lon = REGION_CENTERS[region.lower()]
        waypoints = f"&waypoints={center_lat},{center_lon}"
        print(f"Routing via region anchor: {region} ({center_lat}, {center_lon})")

    link = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={origin_lat},{origin_lon}"
        f"&destination={dest_lat},{dest_lon}"
        f"{waypoints}"
        f"&travelmode=driving"
    )
    return {
        "region": region or "none",
        "google_maps_url": link
    }


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
    the anchor is added as a middle-man reference.
    """

    if region and region.lower() in REGION_CENTERS:
        center_lat, center_lon = REGION_CENTERS[region.lower()]
        print(f"Routing via Yango region anchor: {region} ({center_lat}, {center_lon})")
        # For Yango, we can’t add waypoints directly, but we can log/adjust if needed.

    link = (
        f"yango://route?"
        f"start-lat={origin_lat}&start-lon={origin_lon}"
        f"&end-lat={dest_lat}&end-lon={dest_lon}"
        f"&ref=proxy_location_app"
    )
    return {
        "region": region or "none",
        "yango_url": link
    }
