from fastapi import APIRouter, Query
from typing import Optional
from .region_router import recalculate_origin, resolve_region_offset

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
    Generate Google Maps route link (origin recalibration + destination drift correction).
    Returned link is clean origin → destination.
    """
    new_origin_lat, new_origin_lon = recalculate_origin(origin_lat, origin_lon, region)
    adj_dest_lat, adj_dest_lon = resolve_region_offset(region, dest_lat, dest_lon)

    link = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={new_origin_lat},{new_origin_lon}"
        f"&destination={adj_dest_lat},{adj_dest_lon}"
        f"&travelmode=driving"
    )
    return {
        "region": region or "none",
        "adjusted_origin": [new_origin_lat, new_origin_lon],
        "adjusted_destination": [adj_dest_lat, adj_dest_lon],
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
    Generate Yango deep link (origin recalibration + destination drift correction).
    Returned link is clean origin → destination.
    """
    new_origin_lat, new_origin_lon = recalculate_origin(origin_lat, origin_lon, region)
    adj_dest_lat, adj_dest_lon = resolve_region_offset(region, dest_lat, dest_lon)

    link = (
        f"yango://route?"
        f"start-lat={new_origin_lat}&start-lon={new_origin_lon}"
        f"&end-lat={adj_dest_lat}&end-lon={adj_dest_lon}"
        f"&ref=proxy_location_app"
    )
    return {
        "region": region or "none",
        "adjusted_origin": [new_origin_lat, new_origin_lon],
        "adjusted_destination": [adj_dest_lat, adj_dest_lon],
        "yango_url": link
    }
