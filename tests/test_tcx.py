from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import pytest

from easy_ride.models import Ride, RideSample, RideStats, RideStatus, RoutePoint
from easy_ride.strava.tcx import NS_AE, NS_TCX, generate_tcx


def _make_route_points(n: int = 3):
    """Build a list of minimal route points."""
    return [
        RoutePoint(
            lat=-33.9 + i * 0.001,
            lon=18.4 + i * 0.001,
            elevation_raw=100.0 + i * 5,
            elevation_smoothed=100.0 + i * 5,
            cumulative_distance=i * 100.0,
            gradient_raw=2.0,
            gradient_smoothed=2.0,
            bearing=90.0,
        )
        for i in range(n)
    ]


def _make_samples(n: int = 3, base_time: float = 1700000000.0):
    """Build a list of ride samples."""
    return [
        RideSample(
            timestamp=base_time + i,
            distance=i * 8.5,
            speed=8.5,
            power=200,
            cadence=85,
            heart_rate=140 if i > 0 else 0,
            route_point_idx=min(i, 2),
        )
        for i in range(n)
    ]


def _make_ride(samples=None, stats=None):
    if samples is None:
        samples = _make_samples()
    if stats is None:
        stats = RideStats(
            duration=3.0,
            distance=25.5,
            avg_speed=8.5,
            max_speed=9.0,
            avg_power=200,
            max_power=220,
            avg_cadence=85,
            avg_heart_rate=140,
            total_ascent=10.0,
        )
    return Ride(
        id="test-ride-1",
        route_id="test-route-1",
        status=RideStatus.COMPLETED,
        started_at="2023-11-14T12:00:00Z",
        finished_at="2023-11-14T12:00:03Z",
        stats=stats,
        samples=samples,
    )


@pytest.fixture
def sample_tcx_route():
    from easy_ride.models import Route, RouteStats
    return Route(
        id="test-route-1",
        name="Test Route",
        source_filename="test.gpx",
        created_at="2023-11-14T12:00:00Z",
        stats=RouteStats(
            total_distance=200.0,
            total_ascent=10.0,
            total_descent=5.0,
            min_elevation=100.0,
            max_elevation=110.0,
            max_gradient=5.0,
            min_gradient=-2.0,
            point_count=3,
        ),
        points=_make_route_points(),
    )


class TestTCXGeneration:
    def test_generates_valid_xml(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        assert root.tag == f"{{{NS_TCX}}}TrainingCenterDatabase"

    def test_activity_sport_is_biking(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        activity = root.find(f".//{{{NS_TCX}}}Activity")
        assert activity is not None
        assert activity.get("Sport") == "Biking"

    def test_trackpoint_count_matches_samples(self, sample_tcx_route):
        samples = _make_samples(5)
        ride = _make_ride(samples=samples)
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        trackpoints = root.findall(f".//{{{NS_TCX}}}Trackpoint")
        assert len(trackpoints) == 5

    def test_trackpoint_has_position(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        tp = root.find(f".//{{{NS_TCX}}}Trackpoint")
        pos = tp.find(f"{{{NS_TCX}}}Position")
        assert pos is not None
        lat = pos.find(f"{{{NS_TCX}}}LatitudeDegrees")
        lon = pos.find(f"{{{NS_TCX}}}LongitudeDegrees")
        assert lat is not None and float(lat.text) != 0
        assert lon is not None and float(lon.text) != 0

    def test_trackpoint_has_altitude(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        tp = root.find(f".//{{{NS_TCX}}}Trackpoint")
        alt = tp.find(f"{{{NS_TCX}}}AltitudeMeters")
        assert alt is not None
        assert float(alt.text) == 100.0

    def test_trackpoint_has_extensions(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        tp = root.find(f".//{{{NS_TCX}}}Trackpoint")
        speed = tp.find(f".//{{{NS_AE}}}Speed")
        watts = tp.find(f".//{{{NS_AE}}}Watts")
        assert speed is not None and float(speed.text) > 0
        assert watts is not None and int(watts.text) == 200

    def test_heart_rate_included_when_nonzero(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        trackpoints = root.findall(f".//{{{NS_TCX}}}Trackpoint")
        # First sample has hr=0, second has hr=140
        hr0 = trackpoints[0].find(f"{{{NS_TCX}}}HeartRateBpm")
        hr1 = trackpoints[1].find(f"{{{NS_TCX}}}HeartRateBpm")
        assert hr0 is None  # hr=0 should be omitted
        assert hr1 is not None
        assert hr1.find(f"{{{NS_TCX}}}Value").text == "140"

    def test_cadence_included_when_nonzero(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        tp = root.findall(f".//{{{NS_TCX}}}Trackpoint")[1]
        cad = tp.find(f"{{{NS_TCX}}}Cadence")
        assert cad is not None
        assert cad.text == "85"

    def test_empty_ride_produces_valid_tcx(self, sample_tcx_route):
        ride = _make_ride(samples=[], stats=None)
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        trackpoints = root.findall(f".//{{{NS_TCX}}}Trackpoint")
        assert len(trackpoints) == 0

    def test_lap_has_duration_and_distance(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        lap = root.find(f".//{{{NS_TCX}}}Lap")
        total_time = lap.find(f"{{{NS_TCX}}}TotalTimeSeconds")
        dist = lap.find(f"{{{NS_TCX}}}DistanceMeters")
        assert total_time is not None and float(total_time.text) == 3.0
        assert dist is not None and float(dist.text) == 25.5

    def test_activity_id_is_start_time(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        activity_id = root.find(f".//{{{NS_TCX}}}Id")
        assert activity_id.text == "2023-11-14T12:00:00Z"

    def test_distance_is_cumulative(self, sample_tcx_route):
        ride = _make_ride()
        tcx = generate_tcx(ride, sample_tcx_route)
        root = ET.fromstring(tcx)
        trackpoints = root.findall(f".//{{{NS_TCX}}}Trackpoint")
        distances = [
            float(tp.find(f"{{{NS_TCX}}}DistanceMeters").text) for tp in trackpoints
        ]
        assert distances[0] == 0.0
        assert distances[1] > distances[0]
