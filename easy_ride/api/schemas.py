from __future__ import annotations

from pydantic import BaseModel


class RouteStatsResponse(BaseModel):
    total_distance: float
    total_ascent: float
    total_descent: float
    min_elevation: float
    max_elevation: float
    max_gradient: float
    min_gradient: float
    point_count: int


class RoutePointResponse(BaseModel):
    lat: float
    lon: float
    elevation_raw: float
    elevation_smoothed: float
    cumulative_distance: float
    gradient_raw: float
    gradient_smoothed: float
    bearing: float


class RouteMetadataResponse(BaseModel):
    id: str
    name: str
    source_filename: str
    created_at: str
    stats: RouteStatsResponse


class RouteDetailResponse(RouteMetadataResponse):
    points: list[RoutePointResponse]


class RouteListResponse(BaseModel):
    routes: list[RouteMetadataResponse]


# --- Ride schemas ---


class StartRideRequest(BaseModel):
    route_id: str
    use_simulator: bool = True
    profile_id: str | None = None
    simulator_mode: str = "smart"  # "smart" or "classic"


class RideSampleResponse(BaseModel):
    timestamp: float
    distance: float
    speed: float
    power: int
    cadence: int
    heart_rate: int
    route_point_idx: int


class RideStatsResponse(BaseModel):
    duration: float
    distance: float
    avg_speed: float
    max_speed: float
    avg_power: int
    max_power: int
    avg_cadence: int
    avg_heart_rate: int
    total_ascent: float


class RideMetadataResponse(BaseModel):
    id: str
    route_id: str
    status: str
    started_at: str
    finished_at: str | None = None
    stats: RideStatsResponse | None = None


class RideDetailResponse(RideMetadataResponse):
    samples: list[RideSampleResponse]


class RideListResponse(BaseModel):
    rides: list[RideMetadataResponse]


# --- Device schemas ---


class DiscoveredDeviceResponse(BaseModel):
    address: str
    name: str
    device_type: str
    rssi: int


class DeviceScanResponse(BaseModel):
    devices: list[DiscoveredDeviceResponse]


# --- Settings schemas ---


class SettingsResponse(BaseModel):
    ftp: int
    weight: float
    trainer_device_id: str | None = None
    hrm_device_id: str | None = None
    elevation_smoothing_window: int


class SettingsUpdateRequest(BaseModel):
    ftp: int | None = None
    weight: float | None = None
    trainer_device_id: str | None = None
    hrm_device_id: str | None = None
    elevation_smoothing_window: int | None = None


# --- Trainer Profile schemas ---


class TrainerProfileRequest(BaseModel):
    name: str
    trainer_type: str  # "smart", "classic", "power_meter_only"
    trainer_address: str | None = None
    speed_sensor_address: str | None = None
    cadence_sensor_address: str | None = None
    power_meter_address: str | None = None
    hrm_address: str | None = None
    resistance_factor: float = 20.0
    wheel_circumference: float = 2.105
    is_default: bool = False


class TrainerProfileResponse(BaseModel):
    id: str
    name: str
    trainer_type: str
    trainer_address: str | None = None
    speed_sensor_address: str | None = None
    cadence_sensor_address: str | None = None
    power_meter_address: str | None = None
    hrm_address: str | None = None
    resistance_factor: float
    wheel_circumference: float
    is_default: bool


class TrainerProfileListResponse(BaseModel):
    profiles: list[TrainerProfileResponse]
