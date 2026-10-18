from __future__ import annotations

import uuid
from datetime import datetime, timezone

from easy_ride.exceptions import RouteProcessingError
from easy_ride.gpx.elevation import (
    compute_ascent_descent,
    compute_gradients,
    smooth_elevation,
)
from easy_ride.gpx.geo import compute_bearing, compute_cumulative_distances
from easy_ride.gpx.parser import parse_gpx
from easy_ride.models import Route, RoutePoint, RouteStats


def process_gpx(
    gpx_content: str,
    name: str = "",
    filename: str = "",
    smoothing_window: int = 5,
) -> Route:
    """Full pipeline: GPX XML → Route with computed stats."""
    try:
        raw_points, parsed_name = parse_gpx(gpx_content, filename=filename)
    except Exception as e:
        raise RouteProcessingError(f"Failed to process GPX: {e}") from e

    route_name = name or parsed_name or filename or "Unnamed Route"
    coords = [(p.lat, p.lon) for p in raw_points]
    raw_elevations = [p.elevation for p in raw_points]

    distances = compute_cumulative_distances(coords)
    smoothed_elevations = smooth_elevation(raw_elevations, window=smoothing_window)
    raw_gradients = compute_gradients(distances, raw_elevations)
    smoothed_gradients = compute_gradients(distances, smoothed_elevations)

    bearings = [0.0]
    for i in range(1, len(coords)):
        bearings.append(compute_bearing(*coords[i - 1], *coords[i]))

    ascent, descent = compute_ascent_descent(smoothed_elevations)

    points = []
    for i in range(len(raw_points)):
        points.append(
            RoutePoint(
                lat=raw_points[i].lat,
                lon=raw_points[i].lon,
                elevation_raw=raw_elevations[i],
                elevation_smoothed=smoothed_elevations[i],
                cumulative_distance=distances[i],
                gradient_raw=raw_gradients[i],
                gradient_smoothed=smoothed_gradients[i],
                bearing=bearings[i],
            )
        )

    stats = RouteStats(
        total_distance=distances[-1] if distances else 0.0,
        total_ascent=ascent,
        total_descent=descent,
        min_elevation=min(smoothed_elevations),
        max_elevation=max(smoothed_elevations),
        max_gradient=max(smoothed_gradients),
        min_gradient=min(smoothed_gradients),
        point_count=len(points),
    )

    return Route(
        id=uuid.uuid4().hex,
        name=route_name,
        source_filename=filename,
        created_at=datetime.now(timezone.utc).isoformat(),
        stats=stats,
        points=points,
    )
