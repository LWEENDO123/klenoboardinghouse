# CUZ/routers/region_router.py
from typing import Optional, Tuple
import math

# ✅ Region hubs (real data later)
REGION_CENTERS = {
    "lusaka": (-15.4167, 28.2833),
    "chongwe": (-15.3292, 28.6820),
    "matero": (-15.3885, 28.2478),
    "kafue": (-15.7700, 28.1830),
}

def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two coordinates."""
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


def recalculate_origin(
    origin_lat: float,
    origin_lon: float,
    region: Optional[str] = None,
    drift_limit_km: float = 5.0
) -> Tuple[float, float]:
    """
    If region is provided, use the region center as a reference point
    for recalibration before returning final coordinates.
    """
    if not region or region.lower() not in REGION_CENTERS:
        return origin_lat, origin_lon  # no recalculation needed

    center_lat, center_lon = REGION_CENTERS[region.lower()]
    distance = haversine(origin_lat, origin_lon, center_lat, center_lon)

    # ✅ If far from the region center, route via hub
    if distance > drift_limit_km:
        print(f"[Recalc] Routing via {region} center ({center_lat}, {center_lon}) → Distance: {distance:.2f}km")
        return center_lat, center_lon

    # ✅ If already near, just fine-tune slightly
    offset_lat = center_lat + (origin_lat - center_lat) * 0.95
    offset_lon = center_lon + (origin_lon - center_lon) * 0.95
    print(f"[Recalc] Fine-tuned coordinates for {region}")
    return offset_lat, offset_lon
