from __future__ import annotations


def smooth_elevation(elevations: list[float], window: int = 5) -> list[float]:
    """Centered moving average with shrinking window at edges."""
    if not elevations:
        return []
    n = len(elevations)
    half = window // 2
    result = []
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n - 1, i + half)
        avg = sum(elevations[lo : hi + 1]) / (hi - lo + 1)
        result.append(avg)
    return result


def compute_gradients(
    distances: list[float],
    elevations: list[float],
    min_distance: float = 1.0,
) -> list[float]:
    """Gradient as rise/run percentage. Carries forward when points are too close."""
    if not distances or not elevations:
        return []
    n = len(distances)
    gradients = [0.0]
    last_gradient = 0.0
    for i in range(1, n):
        run = distances[i] - distances[i - 1]
        if run < min_distance:
            gradients.append(last_gradient)
        else:
            rise = elevations[i] - elevations[i - 1]
            last_gradient = (rise / run) * 100
            gradients.append(last_gradient)
    return gradients


def compute_ascent_descent(elevations: list[float]) -> tuple[float, float]:
    """Total ascent and descent from a list of elevations."""
    ascent = 0.0
    descent = 0.0
    for i in range(1, len(elevations)):
        diff = elevations[i] - elevations[i - 1]
        if diff > 0:
            ascent += diff
        else:
            descent += abs(diff)
    return ascent, descent
