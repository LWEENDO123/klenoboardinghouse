# CUZ/routers/directions.py
from fastapi import APIRouter, Query
from typing import Optional
import math
from .region_router import recalculate_origin, resolve_region_offset

router = APIRouter(prefix="/directions", tags=["Directions"])

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
    Regional anchor logic is applied internally (origin recalibration + destination drift correction),
    but the returned link is always a clean origin → destination route.
    """

    # ✅ Apply origin recalibration (snap/fine‑tune relative to anchor if needed)
    adj_origin_lat, adj_origin_lon = recalculate_origin(origin_lat, origin_lon, region)

    # ✅ Apply destination drift correction
    adj_dest_lat, adj_dest_lon = resolve_region_offset(region, dest_lat, dest_lon)

    # ✅ Build clean Google Maps link (no visible waypoints)
    link = (
        f"https://www.google.com/maps/dir/?api=1"
        f"&origin={adj_origin_lat},{adj_origin_lon}"
        f"&destination={adj_dest_lat},{adj_dest_lon}"
        f"&travelmode=driving"
    )

    return {
        "region": region or "direct",
        "origin": [adj_origin_lat, adj_origin_lon],
        "destination": [adj_dest_lat, adj_dest_lon],
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
    Regional anchor logic is applied internally (origin recalibration + destination drift correction),
    but the returned link is always a clean origin → destination route.
    """

    # ✅ Apply origin recalibration
    adj_origin_lat, adj_origin_lon = recalculate_origin(origin_lat, origin_lon, region)

    # ✅ Apply destination drift correction
    adj_dest_lat, adj_dest_lon = resolve_region_offset(region, dest_lat, dest_lon)

    # ✅ Build clean Yango deep link
    link = (
        f"yango://route?"
        f"start-lat={adj_origin_lat}&start-lon={adj_origin_lon}"
        f"&end-lat={adj_dest_lat}&end-lon={adj_dest_lon}"
        f"&ref=proxy_location_app"
    )

    return {
        "region": region or "direct",
        "origin": [adj_origin_lat, adj_origin_lon],
        "destination": [adj_dest_lat, adj_dest_lon],
        "yango_url": link
    }
