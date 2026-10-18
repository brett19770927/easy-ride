from __future__ import annotations

import math

from easy_ride.gpx.geo import (
    compute_bearing,
    compute_cumulative_distances,
    compute_haversine,
)


class TestHaversine:
    def test_same_point_returns_zero(self):
        assert compute_haversine(51.5, -0.1, 51.5, -0.1) == 0.0

    def test_known_distance(self):
        # London to Paris ~341 km
        d = compute_haversine(51.5074, -0.1278, 48.8566, 2.3522)
        assert 340_000 < d < 345_000

    def test_short_distance(self):
        # Two points ~111m apart (0.001 degree latitude)
        d = compute_haversine(51.5000, -0.1000, 51.5010, -0.1000)
        assert 110 < d < 112

    def test_symmetry(self):
        d1 = compute_haversine(51.5, -0.1, 48.8, 2.3)
        d2 = compute_haversine(48.8, 2.3, 51.5, -0.1)
        assert abs(d1 - d2) < 0.001


class TestBearing:
    def test_due_north(self):
        b = compute_bearing(51.5, 0.0, 52.5, 0.0)
        assert abs(b - 0.0) < 1.0

    def test_due_east(self):
        b = compute_bearing(0.0, 0.0, 0.0, 1.0)
        assert abs(b - 90.0) < 1.0

    def test_due_south(self):
        b = compute_bearing(52.5, 0.0, 51.5, 0.0)
        assert abs(b - 180.0) < 1.0

    def test_due_west(self):
        b = compute_bearing(0.0, 1.0, 0.0, 0.0)
        assert abs(b - 270.0) < 1.0

    def test_range_0_360(self):
        b = compute_bearing(51.5, -0.1, 48.8, 2.3)
        assert 0.0 <= b < 360.0


class TestCumulativeDistances:
    def test_empty(self):
        assert compute_cumulative_distances([]) == []

    def test_single_point(self):
        assert compute_cumulative_distances([(51.5, -0.1)]) == [0.0]

    def test_monotonically_increasing(self):
        points = [(51.5, -0.1), (51.501, -0.1), (51.502, -0.1)]
        dists = compute_cumulative_distances(points)
        assert len(dists) == 3
        assert dists[0] == 0.0
        assert dists[1] > 0
        assert dists[2] > dists[1]

    def test_first_is_zero(self):
        points = [(0.0, 0.0), (1.0, 1.0)]
        dists = compute_cumulative_distances(points)
        assert dists[0] == 0.0
