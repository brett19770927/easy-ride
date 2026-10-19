from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from easy_ride.models import Ride, RideSample, Route


NS_TCX = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
NS_AE = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"


def generate_tcx(ride: Ride, route: Route) -> str:
    """Generate a TCX XML string from a completed ride and its route.

    Each RideSample becomes a Trackpoint. Position (lat/lon) and altitude
    come from the route point referenced by sample.route_point_idx.
    """
    ET.register_namespace("", NS_TCX)
    ET.register_namespace("ae", NS_AE)
    ET.register_namespace("xsi", NS_XSI)

    root = ET.Element(
        f"{{{NS_TCX}}}TrainingCenterDatabase",
        attrib={
            f"{{{NS_XSI}}}schemaLocation": (
                f"{NS_TCX} "
                "http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd"
            ),
        },
    )

    activities = ET.SubElement(root, f"{{{NS_TCX}}}Activities")
    activity = ET.SubElement(activities, f"{{{NS_TCX}}}Activity", Sport="Biking")

    id_elem = ET.SubElement(activity, f"{{{NS_TCX}}}Id")
    id_elem.text = ride.started_at

    lap = ET.SubElement(activity, f"{{{NS_TCX}}}Lap", StartTime=ride.started_at)

    if ride.stats:
        total_time = ET.SubElement(lap, f"{{{NS_TCX}}}TotalTimeSeconds")
        total_time.text = f"{ride.stats.duration:.1f}"
        dist = ET.SubElement(lap, f"{{{NS_TCX}}}DistanceMeters")
        dist.text = f"{ride.stats.distance:.1f}"

    intensity = ET.SubElement(lap, f"{{{NS_TCX}}}Intensity")
    intensity.text = "Active"
    trigger = ET.SubElement(lap, f"{{{NS_TCX}}}TriggerMethod")
    trigger.text = "Manual"

    track = ET.SubElement(lap, f"{{{NS_TCX}}}Track")

    for sample in ride.samples:
        tp = _build_trackpoint(sample, route)
        track.append(tp)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _build_trackpoint(sample: RideSample, route: Route) -> ET.Element:
    """Build a single TCX Trackpoint element from a ride sample."""
    tp = ET.Element(f"{{{NS_TCX}}}Trackpoint")

    # Time
    time_elem = ET.SubElement(tp, f"{{{NS_TCX}}}Time")
    dt = datetime.fromtimestamp(sample.timestamp, tz=timezone.utc)
    time_elem.text = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Position from route point
    if sample.route_point_idx < len(route.points):
        point = route.points[sample.route_point_idx]
        position = ET.SubElement(tp, f"{{{NS_TCX}}}Position")
        lat = ET.SubElement(position, f"{{{NS_TCX}}}LatitudeDegrees")
        lat.text = f"{point.lat:.7f}"
        lon = ET.SubElement(position, f"{{{NS_TCX}}}LongitudeDegrees")
        lon.text = f"{point.lon:.7f}"

        alt = ET.SubElement(tp, f"{{{NS_TCX}}}AltitudeMeters")
        alt.text = f"{point.elevation_smoothed:.1f}"

    # Distance (cumulative metres)
    dist = ET.SubElement(tp, f"{{{NS_TCX}}}DistanceMeters")
    dist.text = f"{sample.distance:.1f}"

    # Heart rate
    if sample.heart_rate > 0:
        hr = ET.SubElement(tp, f"{{{NS_TCX}}}HeartRateBpm")
        hr_val = ET.SubElement(hr, f"{{{NS_TCX}}}Value")
        hr_val.text = str(sample.heart_rate)

    # Cadence
    if sample.cadence > 0:
        cad = ET.SubElement(tp, f"{{{NS_TCX}}}Cadence")
        cad.text = str(sample.cadence)

    # Extensions: Speed + Watts
    extensions = ET.SubElement(tp, f"{{{NS_TCX}}}Extensions")
    tpx = ET.SubElement(extensions, f"{{{NS_AE}}}TPX")
    speed_elem = ET.SubElement(tpx, f"{{{NS_AE}}}Speed")
    speed_elem.text = f"{sample.speed:.2f}"
    watts_elem = ET.SubElement(tpx, f"{{{NS_AE}}}Watts")
    watts_elem.text = str(sample.power)

    return tp
