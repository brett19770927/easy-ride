from __future__ import annotations

import asyncio
from typing import Callable, Optional

from easy_ride.ble.device_types import SpeedCadenceData


# 16-bit and 32-bit wraparound limits
_WHEEL_REV_WRAP = 2**32
_CRANK_REV_WRAP = 2**16
_TIME_WRAP = 2**16  # 1/1024s resolution

# Standard wheel circumference (700x25c) in metres
DEFAULT_WHEEL_CIRCUMFERENCE = 2.105


class BLESpeedCadenceSensor:
    """Real BLE Cycling Speed and Cadence (CSC) sensor.

    Wraps pycycling's CSC service. Computes speed from delta wheel revs
    and cadence from delta crank revs, handling wraparound.
    """

    def __init__(
        self,
        address: str,
        wheel_circumference: float = DEFAULT_WHEEL_CIRCUMFERENCE,
    ):
        self._address = address
        self._wheel_circumference = wheel_circumference
        self._client = None
        self._connected = False
        self._handler: Optional[Callable[[SpeedCadenceData], None]] = None

        # Previous values for delta computation
        self._prev_wheel_revs: Optional[int] = None
        self._prev_wheel_time: Optional[int] = None
        self._prev_crank_revs: Optional[int] = None
        self._prev_crank_time: Optional[int] = None
        self._cumulative_wheel_revs: int = 0
        self._cumulative_crank_revs: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        from bleak import BleakClient

        self._client = BleakClient(self._address)
        await self._client.connect()
        self._connected = True

    async def disconnect(self) -> None:
        await self.stop_notifications()
        if self._client:
            await self._client.disconnect()
        self._connected = False

    def set_data_handler(self, handler: Callable[[SpeedCadenceData], None]) -> None:
        self._handler = handler

    def _on_csc_data(self, data) -> None:
        """Handle raw pycycling CSC measurement."""
        wheel_speed = 0.0
        cadence = 0

        # Wheel speed from cumulative wheel revs + last wheel event time
        if (
            data.cumulative_wheel_revolutions is not None
            and data.last_wheel_event_time is not None
        ):
            if self._prev_wheel_revs is not None:
                d_revs = (
                    data.cumulative_wheel_revolutions - self._prev_wheel_revs
                ) % _WHEEL_REV_WRAP
                d_time = (
                    data.last_wheel_event_time - self._prev_wheel_time
                ) % _TIME_WRAP
                if d_time > 0 and d_revs > 0:
                    dt_seconds = d_time / 1024.0
                    wheel_speed = (d_revs * self._wheel_circumference) / dt_seconds
                    self._cumulative_wheel_revs += d_revs
            self._prev_wheel_revs = data.cumulative_wheel_revolutions
            self._prev_wheel_time = data.last_wheel_event_time

        # Cadence from cumulative crank revs + last crank event time
        if (
            data.cumulative_crank_revolutions is not None
            and data.last_crank_event_time is not None
        ):
            if self._prev_crank_revs is not None:
                d_revs = (
                    data.cumulative_crank_revolutions - self._prev_crank_revs
                ) % _CRANK_REV_WRAP
                d_time = (
                    data.last_crank_event_time - self._prev_crank_time
                ) % _TIME_WRAP
                if d_time > 0 and d_revs > 0:
                    dt_seconds = d_time / 1024.0
                    cadence = int(round(d_revs / dt_seconds * 60.0))
                    self._cumulative_crank_revs += d_revs
            self._prev_crank_revs = data.cumulative_crank_revolutions
            self._prev_crank_time = data.last_crank_event_time

        if self._handler:
            self._handler(SpeedCadenceData(
                wheel_speed=wheel_speed,
                cadence=cadence,
                cumulative_wheel_revs=self._cumulative_wheel_revs,
                cumulative_crank_revs=self._cumulative_crank_revs,
            ))

    async def start_notifications(self) -> None:
        from pycycling.cycling_speed_cadence_service import CyclingSpeedCadenceService

        self._csc = CyclingSpeedCadenceService(self._client)
        self._csc.set_csc_measurement_handler(self._on_csc_data)
        await self._csc.enable_csc_measurement_notifications()

    async def stop_notifications(self) -> None:
        if hasattr(self, "_csc"):
            try:
                await self._csc.disable_csc_measurement_notifications()
            except Exception:
                pass
