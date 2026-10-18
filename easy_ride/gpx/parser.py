from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from easy_ride.exceptions import GPXParseError


@dataclass
class RawTrackpoint:
    lat: float
    lon: float
    elevation: float


GPX_NAMESPACES = {
    "1.1": "http://www.topografix.com/GPX/1/1",
    "1.0": "http://www.topografix.com/GPX/1/0",
}


def parse_gpx(gpx_content: str, filename: str = "") -> tuple[list[RawTrackpoint], str]:
    """Parse GPX XML and return (trackpoints, route_name)."""
    try:
        root = ET.fromstring(gpx_content)
    except ET.ParseError as e:
        raise GPXParseError(f"Invalid XML: {e}", filename=filename) from e

    ns = _detect_namespace(root)
    name = _extract_name(root, ns)
    points = _extract_trackpoints(root, ns, filename)

    if not points:
        points = _extract_routepoints(root, ns, filename)

    if not points:
        raise GPXParseError("No trackpoints or routepoints found", filename=filename)

    return points, name


def _detect_namespace(root: ET.Element) -> str:
    tag = root.tag
    if "{" in tag:
        uri = tag.split("}")[0].lstrip("{")
        return uri
    return ""


def _extract_name(root: ET.Element, ns: str) -> str:
    prefix = f"{{{ns}}}" if ns else ""
    for path in [
        f"{prefix}trk/{prefix}name",
        f"{prefix}rte/{prefix}name",
        f"{prefix}metadata/{prefix}name",
    ]:
        el = root.find(path)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def _extract_trackpoints(
    root: ET.Element, ns: str, filename: str,
) -> list[RawTrackpoint]:
    prefix = f"{{{ns}}}" if ns else ""
    points = []
    for trkpt in root.iter(f"{prefix}trkpt"):
        points.append(_parse_point(trkpt, prefix, filename))
    return points


def _extract_routepoints(
    root: ET.Element, ns: str, filename: str,
) -> list[RawTrackpoint]:
    prefix = f"{{{ns}}}" if ns else ""
    points = []
    for rtept in root.iter(f"{prefix}rtept"):
        points.append(_parse_point(rtept, prefix, filename))
    return points


def _parse_point(el: ET.Element, prefix: str, filename: str) -> RawTrackpoint:
    lat_s = el.get("lat")
    lon_s = el.get("lon")
    if lat_s is None or lon_s is None:
        raise GPXParseError("Trackpoint missing lat/lon", filename=filename)
    try:
        lat = float(lat_s)
        lon = float(lon_s)
    except ValueError:
        raise GPXParseError(f"Invalid lat/lon: {lat_s}, {lon_s}", filename=filename)

    ele_el = el.find(f"{prefix}ele")
    elevation = 0.0
    if ele_el is not None and ele_el.text:
        try:
            elevation = float(ele_el.text.strip())
        except ValueError:
            elevation = 0.0

    return RawTrackpoint(lat=lat, lon=lon, elevation=elevation)
