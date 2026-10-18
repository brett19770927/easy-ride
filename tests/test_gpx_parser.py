from __future__ import annotations

import pytest

from easy_ride.exceptions import GPXParseError
from easy_ride.gpx.parser import parse_gpx


class TestParseGPX:
    def test_simple_loop(self, simple_loop_gpx):
        points, name = parse_gpx(simple_loop_gpx)
        assert name == "Simple Loop"
        assert len(points) == 5
        assert points[0].lat == pytest.approx(51.5074)
        assert points[0].lon == pytest.approx(-0.1278)
        assert points[0].elevation == pytest.approx(10.0)

    def test_mountain_climb(self, mountain_climb_gpx):
        points, name = parse_gpx(mountain_climb_gpx)
        assert name == "Mountain Climb"
        assert len(points) == 10
        assert points[-1].elevation == pytest.approx(1500.0)

    def test_invalid_xml(self):
        with pytest.raises(GPXParseError, match="Invalid XML"):
            parse_gpx("<not valid xml")

    def test_no_trackpoints(self):
        gpx = '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"></gpx>'
        with pytest.raises(GPXParseError, match="No trackpoints"):
            parse_gpx(gpx)

    def test_gpx_10_namespace(self):
        gpx = """<?xml version="1.0"?>
        <gpx version="1.0" xmlns="http://www.topografix.com/GPX/1/0">
          <trk><name>Old Format</name><trkseg>
            <trkpt lat="51.5" lon="-0.1"><ele>10</ele></trkpt>
            <trkpt lat="51.6" lon="-0.2"><ele>20</ele></trkpt>
          </trkseg></trk>
        </gpx>"""
        points, name = parse_gpx(gpx)
        assert name == "Old Format"
        assert len(points) == 2

    def test_routepoints(self):
        gpx = """<?xml version="1.0"?>
        <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
          <rte><name>Route Test</name>
            <rtept lat="51.5" lon="-0.1"><ele>10</ele></rtept>
            <rtept lat="51.6" lon="-0.2"><ele>20</ele></rtept>
          </rte>
        </gpx>"""
        points, name = parse_gpx(gpx)
        assert name == "Route Test"
        assert len(points) == 2

    def test_missing_elevation_defaults_zero(self):
        gpx = """<?xml version="1.0"?>
        <gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
          <trk><trkseg>
            <trkpt lat="51.5" lon="-0.1"></trkpt>
          </trkseg></trk>
        </gpx>"""
        points, _ = parse_gpx(gpx)
        assert points[0].elevation == 0.0

    def test_filename_in_error(self):
        with pytest.raises(GPXParseError) as exc_info:
            parse_gpx("<bad>", filename="test.gpx")
        assert "test.gpx" in str(exc_info.value)
