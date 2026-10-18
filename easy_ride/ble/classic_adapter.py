from __future__ import annotations

from typing import Callable, Optional

from easy_ride.ble.device_types import (
    PowerMeterData,
    PowerMeterDevice,
    SpeedCadenceData,
    SpeedCadenceSensor,
    TrainerData,
)


class ClassicTrainerAdapter:
    """Adapts classic/dumb trainer sensors to the TrainerDevice protocol.

    Composes a speed/cadence sensor and an optional power meter.
    Control methods (set_target_gradient, etc.) are no-ops since you can't
    control a dumb trainer electronically.

    When a power meter is present, uses its power directly.
    Otherwise estimates power from wheel speed using resistance_factor:
        power = speed * resistance_factor
    """

    def __init__(
        self,
        speed_sensor: Optional[SpeedCadenceSensor] = None,
        power_meter: Optional[PowerMeterDevice] = None,
        resistance_factor: float = 20.0,
    ):
        if speed_sensor is None and power_meter is None:
            raise ValueError("At least one of speed_sensor or power_meter is required")
        self._speed_sensor = speed_sensor
        self._power_meter = power_meter
        self._resistance_factor = resistance_factor
        self._connected = False
        self._handler: Optional[Callable[[TrainerData], None]] = None

        # Latest data from each sensor
        self._latest_speed: float = 0.0
        self._latest_cadence: int = 0
        self._latest_power: int = 0
        self._cumulative_distance: float = 0.0
        self._has_pm_power: bool = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self._speed_sensor:
            await self._speed_sensor.connect()
        if self._power_meter:
            await self._power_meter.connect()
        self._connected = True

    async def disconnect(self) -> None:
        await self.stop_notifications()
        if self._speed_sensor:
            await self._speed_sensor.disconnect()
        if self._power_meter:
            await self._power_meter.disconnect()
        self._connected = False

    def set_data_handler(self, handler: Callable[[TrainerData], None]) -> None:
        self._handler = handler

    def _on_speed_cadence_data(self, data: SpeedCadenceData) -> None:
        self._latest_speed = data.wheel_speed
        self._latest_cadence = data.cadence
        if not self._has_pm_power:
            # Estimate power from speed when no power meter
            self._latest_power = max(0, int(data.wheel_speed * self._resistance_factor))
        self._emit()

    def _on_power_data(self, data: PowerMeterData) -> None:
        self._has_pm_power = True
        self._latest_power = data.instant_power
        # Use PM cadence if available and no speed sensor for cadence
        if data.cadence > 0:
            self._latest_cadence = data.cadence
        self._emit()

    def _emit(self) -> None:
        """Emit a TrainerData update combining all sensor data."""
        # Accumulate distance from speed (1Hz assumption)
        self._cumulative_distance += self._latest_speed

        resistance = 0.0  # Can't read resistance from a dumb trainer
        data = TrainerData(
            instant_speed=self._latest_speed,
            instant_cadence=self._latest_cadence,
            instant_power=self._latest_power,
            resistance_level=resistance,
            distance=self._cumulative_distance,
        )
        if self._handler:
            self._handler(data)

    async def start_notifications(self) -> None:
        if self._speed_sensor:
            self._speed_sensor.set_data_handler(self._on_speed_cadence_data)
            await self._speed_sensor.start_notifications()
        if self._power_meter:
            self._power_meter.set_data_handler(self._on_power_data)
            await self._power_meter.start_notifications()

    async def stop_notifications(self) -> None:
        if self._speed_sensor:
            await self._speed_sensor.stop_notifications()
        if self._power_meter:
            await self._power_meter.stop_notifications()

    # Control methods are no-ops for classic trainers
    async def set_target_gradient(self, percent: float) -> None:
        pass

    async def set_target_power(self, watts: int) -> None:
        pass

    async def set_target_resistance(self, level: float) -> None:
        pass
