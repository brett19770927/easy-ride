from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


@dataclass
class RoutePoint:
    lat: float
    lon: float
    elevation_raw: float
    elevation_smoothed: float
    cumulative_distance: float
    gradient_raw: float
    gradient_smoothed: float
    bearing: float


@dataclass
class RouteStats:
    total_distance: float
    total_ascent: float
    total_descent: float
    min_elevation: float
    max_elevation: float
    max_gradient: float
    min_gradient: float
    point_count: int


@dataclass
class Route:
    id: str
    name: str
    source_filename: str
    created_at: str
    stats: RouteStats
    points: list[RoutePoint] = field(default_factory=list)


class RideStatus(Enum):
    PAUSED = "paused"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class RideSample:
    timestamp: float
    distance: float
    speed: float
    power: int
    cadence: int
    heart_rate: int
    route_point_idx: int


@dataclass
class RideStats:
    duration: float
    distance: float
    avg_speed: float
    max_speed: float
    avg_power: int
    max_power: int
    avg_cadence: int
    avg_heart_rate: int
    total_ascent: float


@dataclass
class Ride:
    id: str
    route_id: str
    status: RideStatus
    started_at: str
    finished_at: Optional[str] = None
    stats: Optional[RideStats] = None
    samples: list[RideSample] = field(default_factory=list)


class TrainerType(Enum):
    SMART = "smart"
    CLASSIC = "classic"
    POWER_METER_ONLY = "power_meter_only"


@dataclass
class TrainerProfile:
    id: str
    name: str
    trainer_type: TrainerType
    trainer_address: Optional[str] = None
    speed_sensor_address: Optional[str] = None
    cadence_sensor_address: Optional[str] = None
    power_meter_address: Optional[str] = None
    hrm_address: Optional[str] = None
    resistance_factor: float = 20.0
    wheel_circumference: float = 2.105
    is_default: bool = False


@dataclass
class UserSettings:
    ftp: int = 200
    weight: float = 75.0
    trainer_device_id: Optional[str] = None
    hrm_device_id: Optional[str] = None
    strava_access_token: Optional[str] = None
    strava_refresh_token: Optional[str] = None
    elevation_smoothing_window: int = 5
