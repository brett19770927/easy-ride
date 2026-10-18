from __future__ import annotations

import math


EARTH_RADIUS = 6_371_000  # meters


def compute_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two GPS coordinates using the haversine formula."""
    rlat1, rlon1, rlat2, rlon2 = (
        math.radians(lat1),
        math.radians(lon1),
        math.radians(lat2),
        math.radians(lon2),
    )
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1

    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS * c


def compute_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees (0-360) from point 1 to point 2."""
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    bearing = math.degrees(math.atan2(x, y))
    return bearing % 360


def compute_cumulative_distances(
    points: list[tuple[float, float]],
) -> list[float]:
    """Cumulative distances in meters for a list of (lat, lon) tuples."""
    if not points:
        return []
    distances = [0.0]
    for i in range(1, len(points)):
        d = compute_haversine(
            points[i - 1][0], points[i - 1][1],
            points[i][0], points[i][1],
        )
        distances.append(distances[-1] + d)
    return distances
