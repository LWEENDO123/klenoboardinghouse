# CUZ/routers/region_router.py
from typing import Optional, Tuple
import math

# ✅ Regional anchors (act as subnet gateways)
REGION_CENTERS = {
    "kalingalinga": (-15.404706, 28.331178),  # Cavendish Medical, UNZA, Chreso, UNILUS Main
    "cuz": (-15.403314, 28.278487),           # Cavendish University Main Campus
}

# ✅ Boarding house coordinates under Kalingalinga region
KALINGALINGA_REGION = {
    "beza_accommodation": (-15.405442, 28.336161),
    "petronela_boardinghouse": (-15.402681, 28.334535),
    "chanowa_boardinghouse": (-15.402292, 28.337543),
    "ms_phonebe_boardinghouse": (-15.408036, 28.338331),
    "clempark_boardinghouse": (-15.409761, 28.325521),
    "big_brother_accommodation": (-15.412493, 28.321370),
    "mr_banda_kasoma_boardinghouse": (-15.412121, 28.319557),
    "house_of_grace_boardinghouse": (-15.403709, 28.329916),
    "georges_boardinghouse": (-15.403711, 28.332782),
    "classy_boardinghouse": (-15.408111, 28.344221),
}

# ✅ Boarding house coordinates under CUZ region
CUZ_AREA = {
    "Mr solomon": (-15.405278, 28.283278),
    "mr_tembo_boardinghouse": (-15.386688, 28.284536),
    "mr_tembo_second_boardinghouse": (-15.386915, 28.284082),
}


def haversine(lat1, lon1, lat2, lon2):
    """Distance in km between two coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lat2 - lon1)
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


def resolve_region_offset(
    region: Optional[str],
    dest_lat: float,
    dest_lon: float,
    correction_m: float = 8.0
) -> Tuple[float, float]:
    """
    Applies a small directional offset (in meters) based on regional center
    to correct visual drift on Google/Yango maps.
    """
    if not region or region.lower() not in REGION_CENTERS:
        return dest_lat, dest_lon

    center_lat, center_lon = REGION_CENTERS[region.lower()]

    # Approx. meters per degree at this latitude
    m_per_deg_lat = 111_320
    m_per_deg_lon = 111_320 * math.cos(math.radians(center_lat))

    # Calculate distance and direction vector
    diff_lat = dest_lat - center_lat
    diff_lon = dest_lon - center_lon

    # Apply subtle correction (default 8 m depending on direction)
    adj_lat = dest_lat + (correction_m / m_per_deg_lat) * (1 if diff_lat >= 0 else -1)
    adj_lon = dest_lon + (correction_m / m_per_deg_lon) * (1 if diff_lon >= 0 else -1)

    print(f"[Offset] Applied {correction_m}m drift correction for {region}")
    return round(adj_lat, 6), round(adj_lon, 6)


def get_boardinghouse_coords(region: str, house_id: str) -> Tuple[float, float]:
    """
    Lookup boarding house coordinates by ID under a given region.
    """
    region = region.lower()
    if region == "kalingalinga":
        coords = KALINGALINGA_REGION.get(house_id)
        if coords:
            return coords
        else:
            raise ValueError(f"Boarding house {house_id} not found in {region} region")
    elif region == "cuz":
        coords = CUZ_AREA.get(house_id)
        if coords:
            return coords
        else:
            raise ValueError(f"Boarding house {house_id} not found in {region} region")
    else:
        raise ValueError(f"Region {region} not supported")
