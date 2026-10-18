from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol, runtime_checkable


class DeviceType(Enum):
    TRAINER = "trainer"
    HRM = "hrm"
    UNKNOWN = "unknown"


@dataclass
class TrainerData:
    instant_speed: float  # m/s
    instant_cadence: int  # rpm
    instant_power: int  # watts
    resistance_level: float  # 0.0-1.0
    distance: float  # metres cumulative


@dataclass
class HRMData:
    bpm: int
    sensor_contact: bool


@dataclass
class DiscoveredDevice:
    address: str
    name: str
    device_type: DeviceType
    rssi: int


@runtime_checkable
class TrainerDevice(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    def set_data_handler(self, handler: Callable[[TrainerData], None]) -> None: ...
    async def start_notifications(self) -> None: ...
    async def stop_notifications(self) -> None: ...
    async def set_target_gradient(self, percent: float) -> None: ...
    async def set_target_power(self, watts: int) -> None: ...
    async def set_target_resistance(self, level: float) -> None: ...

    @property
    def is_connected(self) -> bool: ...


@runtime_checkable
class HRMDevice(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    def set_data_handler(self, handler: Callable[[HRMData], None]) -> None: ...
    async def start_notifications(self) -> None: ...
    async def stop_notifications(self) -> None: ...

    @property
    def is_connected(self) -> bool: ...
