from __future__ import annotations


class EasyRideError(Exception):
    pass


class GPXParseError(EasyRideError):
    def __init__(self, message: str, filename: str = "", line: int = 0):
        self.filename = filename
        self.line = line
        parts = []
        if filename:
            parts.append(filename)
        if line:
            parts.append(f"line {line}")
        prefix = ", ".join(parts)
        if prefix:
            super().__init__(f"{prefix}: {message}")
        else:
            super().__init__(message)


class RouteProcessingError(EasyRideError):
    pass


class RouteNotFoundError(EasyRideError):
    def __init__(self, route_id: str):
        self.route_id = route_id
        super().__init__(f"Route not found: {route_id}")


class DatabaseError(EasyRideError):
    pass


class BLEError(EasyRideError):
    pass


class DeviceNotFoundError(BLEError):
    def __init__(self, device_id: str):
        self.device_id = device_id
        super().__init__(f"Device not found: {device_id}")


class DeviceConnectionError(BLEError):
    def __init__(self, device_id: str, reason: str = ""):
        self.device_id = device_id
        self.reason = reason
        msg = f"Failed to connect to device: {device_id}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)


class RideNotFoundError(EasyRideError):
    def __init__(self, ride_id: str):
        self.ride_id = ride_id
        super().__init__(f"Ride not found: {ride_id}")


class ProfileNotFoundError(EasyRideError):
    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        super().__init__(f"Trainer profile not found: {profile_id}")


class RideStateError(EasyRideError):
    def __init__(self, ride_id: str, current: str, attempted: str):
        self.ride_id = ride_id
        self.current = current
        self.attempted = attempted
        super().__init__(
            f"Ride {ride_id}: cannot transition from {current} to {attempted}"
        )
