from __future__ import annotations

from typing import Callable, Optional

from easy_ride.ble.device_types import HRMData
from easy_ride.exceptions import DeviceConnectionError


class BLEHeartRateMonitor:
    """Real BLE heart rate monitor using pycycling.

    Connects to standard Bluetooth Heart Rate Service devices.
    """

    def __init__(self, address: str):
        self._address = address
        self._client = None
        self._hrm = None
        self._handler: Optional[Callable[[HRMData], None]] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        from bleak import BleakClient
        from pycycling.heart_rate_service import HeartRateService

        try:
            self._client = BleakClient(self._address)
            await self._client.connect()
            self._hrm = HeartRateService(self._client)
            self._connected = True
        except Exception as e:
            raise DeviceConnectionError(self._address, str(e))

    async def disconnect(self) -> None:
        await self.stop_notifications()
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._connected = False

    def set_data_handler(self, handler: Callable[[HRMData], None]) -> None:
        self._handler = handler

    def _on_hr_data(self, data) -> None:
        bpm = int(getattr(data, "bpm", 0) or getattr(data, "heart_rate", 0) or 0)
        contact = bool(getattr(data, "sensor_contact", True))
        hrm_data = HRMData(bpm=bpm, sensor_contact=contact)
        if self._handler:
            self._handler(hrm_data)

    async def start_notifications(self) -> None:
        if self._hrm:
            self._hrm.set_hr_measurement_handler(self._on_hr_data)
            await self._hrm.enable_hr_measurement_notifications()

    async def stop_notifications(self) -> None:
        if self._hrm:
            try:
                await self._hrm.disable_hr_measurement_notifications()
            except Exception:
                pass
