from __future__ import annotations

import pytest

from easy_ride.gpx.processor import process_gpx
from easy_ride.models import Route


class TestProcessGPX:
    def test_returns_route(self, simple_loop_gpx):
        route = process_gpx(simple_loop_gpx, filename="simple_loop.gpx")
        assert isinstance(route, Route)
        assert route.name == "Simple Loop"
        assert route.source_filename == "simple_loop.gpx"
        assert len(route.id) == 32  # uuid hex

    def test_point_count_matches(self, simple_loop_gpx):
        route = process_gpx(simple_loop_gpx)
        assert route.stats.point_count == 5
        assert len(route.points) == 5

    def test_cumulative_distances(self, simple_loop_gpx):
        route = process_gpx(simple_loop_gpx)
        assert route.points[0].cumulative_distance == 0.0
        for i in range(1, len(route.points)):
            assert route.points[i].cumulative_distance > route.points[i - 1].cumulative_distance

    def test_stats_computed(self, mountain_climb_gpx):
        route = process_gpx(mountain_climb_gpx)
        assert route.stats.total_distance > 0
        assert route.stats.total_ascent > 0
        assert route.stats.max_elevation > route.stats.min_elevation

    def test_custom_name_overrides(self, simple_loop_gpx):
        route = process_gpx(simple_loop_gpx, name="My Custom Route")
        assert route.name == "My Custom Route"

    def test_gradient_extremes_in_stats(self, mountain_climb_gpx):
        route = process_gpx(mountain_climb_gpx)
        assert route.stats.max_gradient > 0  # uphill route

    def test_bearings_computed(self, simple_loop_gpx):
        route = process_gpx(simple_loop_gpx)
        assert route.points[0].bearing == 0.0  # first point has no bearing
        for p in route.points[1:]:
            assert 0.0 <= p.bearing < 360.0

    def test_elevation_smoothing(self, mountain_climb_gpx):
        route = process_gpx(mountain_climb_gpx, smoothing_window=5)
        # Smoothed should differ from raw for interior points
        has_diff = any(
            p.elevation_smoothed != p.elevation_raw for p in route.points
        )
        assert has_diff

    def test_created_at_is_iso(self, simple_loop_gpx):
        route = process_gpx(simple_loop_gpx)
        assert "T" in route.created_at  # ISO format
