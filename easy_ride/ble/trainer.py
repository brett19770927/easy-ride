from __future__ import annotations

from typing import Callable, Optional

from easy_ride.ble.device_types import TrainerData
from easy_ride.exceptions import DeviceConnectionError


class FTMSTrainer:
    """Real BLE smart trainer using FTMS protocol via pycycling.

    Requires bleak and pycycling. Connects to FTMS-compatible trainers.
    """

    def __init__(self, address: str):
        self._address = address
        self._client = None
        self._ftms = None
        self._handler: Optional[Callable[[TrainerData], None]] = None
        self._connected = False
        self._cumulative_distance: float = 0.0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        from bleak import BleakClient
        from pycycling.fitness_machine_service import FitnessMachineService

        try:
            self._client = BleakClient(self._address)
            await self._client.connect()
            self._ftms = FitnessMachineService(self._client)
            self._connected = True
        except Exception as e:
            raise DeviceConnectionError(self._address, str(e))

    async def disconnect(self) -> None:
        await self.stop_notifications()
        if self._client and self._client.is_connected:
            await self._client.disconnect()
        self._connected = False

    def set_data_handler(self, handler: Callable[[TrainerData], None]) -> None:
        self._handler = handler

    def _on_indoor_bike_data(self, data) -> None:
        speed = getattr(data, "instant_speed", 0.0) / 3.6  # km/h → m/s
        cadence = int(getattr(data, "instant_cadence", 0) or 0)
        power = int(getattr(data, "instant_power", 0) or 0)
        resistance = getattr(data, "resistance_level", 0.0) or 0.0
        # pycycling distance in metres
        dist = getattr(data, "total_distance", None)
        if dist is not None:
            self._cumulative_distance = float(dist)
        else:
            self._cumulative_distance += speed  # Fallback: 1Hz assumption

        trainer_data = TrainerData(
            instant_speed=speed,
            instant_cadence=cadence,
            instant_power=power,
            resistance_level=resistance,
            distance=self._cumulative_distance,
        )
        if self._handler:
            self._handler(trainer_data)

    async def start_notifications(self) -> None:
        if self._ftms:
            self._ftms.set_indoor_bike_data_handler(self._on_indoor_bike_data)
            await self._ftms.enable_indoor_bike_data_notify()

    async def stop_notifications(self) -> None:
        if self._ftms:
            try:
                await self._ftms.disable_indoor_bike_data_notify()
            except Exception:
                pass

    async def set_target_gradient(self, percent: float) -> None:
        if self._ftms:
            from easy_ride.ride.physics import ftms_grade_from_gradient
            grade = ftms_grade_from_gradient(percent)
            try:
                await self._ftms.set_simulation_parameters(grade, 0, 0, 0)
            except Exception:
                pass

    async def set_target_power(self, watts: int) -> None:
        if self._ftms:
            try:
                await self._ftms.set_target_power(watts)
            except Exception:
                pass

    async def set_target_resistance(self, level: float) -> None:
        if self._ftms:
            try:
                await self._ftms.set_target_resistance_level(int(level * 100))
            except Exception:
                pass
