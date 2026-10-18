from __future__ import annotations

import asyncio
from typing import Callable, Optional

from easy_ride.ble.device_types import PowerMeterData


_CRANK_REV_WRAP = 2**16
_TIME_WRAP = 2**16  # 1/1024s resolution


class BLEPowerMeter:
    """Real BLE Cycling Power Service (CPS) power meter.

    Reads instant power directly. Derives cadence from crank rev deltas
    if the power meter reports cumulative crank revolutions.
    """

    def __init__(self, address: str):
        self._address = address
        self._client = None
        self._connected = False
        self._handler: Optional[Callable[[PowerMeterData], None]] = None

        self._prev_crank_revs: Optional[int] = None
        self._prev_crank_time: Optional[int] = None

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

    def set_data_handler(self, handler: Callable[[PowerMeterData], None]) -> None:
        self._handler = handler

    def _on_power_data(self, data) -> None:
        """Handle raw pycycling CPS measurement."""
        power = data.instantaneous_power if data.instantaneous_power is not None else 0
        cadence = 0

        # Derive cadence from crank rev deltas if available
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
            self._prev_crank_revs = data.cumulative_crank_revolutions
            self._prev_crank_time = data.last_crank_event_time

        if self._handler:
            self._handler(PowerMeterData(
                instant_power=power,
                cadence=cadence,
            ))

    async def start_notifications(self) -> None:
        from pycycling.cycling_power_service import CyclingPowerService

        self._cps = CyclingPowerService(self._client)
        self._cps.set_cycling_power_measurement_handler(self._on_power_data)
        await self._cps.enable_cycling_power_measurement_notifications()

    async def stop_notifications(self) -> None:
        if hasattr(self, "_cps"):
            try:
                await self._cps.disable_cycling_power_measurement_notifications()
            except Exception:
                pass
