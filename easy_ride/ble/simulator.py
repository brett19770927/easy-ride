from __future__ import annotations

import asyncio
import random
from typing import Callable, Optional

from easy_ride.ble.device_types import (
    HRMData,
    PowerMeterData,
    SpeedCadenceData,
    TrainerData,
)
from easy_ride.ride.physics import effort_fraction, speed_from_power


class SimulatedTrainer:
    """Simulated smart trainer that generates realistic cycling data.

    Power responds to gradient changes. Speed derived from physics.
    Cadence drops on steep climbs.
    """

    def __init__(self, ftp: int = 200, weight: float = 75.0):
        self._ftp = ftp
        self._weight = weight
        self._connected = False
        self._handler: Optional[Callable[[TrainerData], None]] = None
        self._task: Optional[asyncio.Task] = None
        self._gradient: float = 0.0
        self._target_power: Optional[int] = None
        self._target_resistance: Optional[float] = None
        self._cumulative_distance: float = 0.0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        await self.stop_notifications()
        self._connected = False

    def set_data_handler(self, handler: Callable[[TrainerData], None]) -> None:
        self._handler = handler

    async def start_notifications(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._generate_loop())

    async def stop_notifications(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def set_target_gradient(self, percent: float) -> None:
        self._gradient = percent

    async def set_target_power(self, watts: int) -> None:
        self._target_power = watts
        self._target_resistance = None

    async def set_target_resistance(self, level: float) -> None:
        self._target_resistance = level
        self._target_power = None

    def _compute_power(self) -> int:
        if self._target_power is not None:
            noise = random.gauss(0, self._target_power * 0.03)
            return max(0, int(self._target_power + noise))

        gradient_fraction = self._gradient / 100.0
        # Base power scales with gradient — rider works harder uphill
        gradient_factor = 1.0 + max(0, gradient_fraction) * 8.0
        # Downhill: rider eases off
        if gradient_fraction < 0:
            gradient_factor = max(0.3, 1.0 + gradient_fraction * 2.0)
        base = self._ftp * 0.65 * gradient_factor
        noise = random.gauss(0, base * 0.05)
        return max(0, int(base + noise))

    def _compute_cadence(self, power: int) -> int:
        # Cadence drops on steep climbs
        if self._gradient > 8:
            base = 65
        elif self._gradient > 4:
            base = 75
        else:
            base = 85
        # Higher power slightly increases cadence variation
        noise = random.randint(-3, 3)
        return max(30, base + noise)

    async def _generate_loop(self) -> None:
        try:
            while True:
                power = self._compute_power()
                cadence = self._compute_cadence(power)
                gradient_fraction = self._gradient / 100.0
                speed = speed_from_power(
                    float(power), gradient_fraction, self._weight
                )
                self._cumulative_distance += speed  # 1Hz → 1 second of travel
                resistance = max(0.0, min(1.0, self._gradient / 20.0))

                data = TrainerData(
                    instant_speed=speed,
                    instant_cadence=cadence,
                    instant_power=power,
                    resistance_level=resistance,
                    distance=self._cumulative_distance,
                )
                if self._handler:
                    self._handler(data)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise


class SimulatedHRM:
    """Simulated heart rate monitor with realistic HR drift.

    HR drifts toward an effort-based target with ~30s time constant.
    """

    def __init__(self, resting_hr: int = 65, max_hr: int = 185):
        self._resting_hr = resting_hr
        self._max_hr = max_hr
        self._connected = False
        self._handler: Optional[Callable[[HRMData], None]] = None
        self._task: Optional[asyncio.Task] = None
        self._current_hr: float = float(resting_hr)
        self._effort: float = 0.0  # 0.0-1.0+

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        await self.stop_notifications()
        self._connected = False

    def set_data_handler(self, handler: Callable[[HRMData], None]) -> None:
        self._handler = handler

    def set_effort(self, fraction: float) -> None:
        """Set current effort level (power/FTP ratio)."""
        self._effort = max(0.0, fraction)

    async def start_notifications(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._generate_loop())

    async def stop_notifications(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _target_hr(self) -> float:
        hr_range = self._max_hr - self._resting_hr
        # Effort of 1.0 (FTP) ≈ 85-90% of max HR
        return self._resting_hr + hr_range * min(1.0, self._effort * 0.88)

    async def _generate_loop(self) -> None:
        try:
            while True:
                target = self._target_hr()
                # Exponential drift: ~30s time constant at 1Hz
                alpha = 1.0 / 30.0
                self._current_hr += alpha * (target - self._current_hr)
                noise = random.gauss(0, 1.0)
                bpm = int(max(self._resting_hr, self._current_hr + noise))
                bpm = min(bpm, self._max_hr)

                data = HRMData(bpm=bpm, sensor_contact=True)
                if self._handler:
                    self._handler(data)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise


class SimulatedSpeedCadenceSensor:
    """Simulated CSC sensor for testing classic trainer setups.

    Generates wheel speed and cadence based on an effort fraction.
    """

    def __init__(self, wheel_circumference: float = 2.105):
        self._wheel_circumference = wheel_circumference
        self._connected = False
        self._handler: Optional[Callable[[SpeedCadenceData], None]] = None
        self._task: Optional[asyncio.Task] = None
        self._effort: float = 0.5
        self._cumulative_wheel_revs: int = 0
        self._cumulative_crank_revs: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        await self.stop_notifications()
        self._connected = False

    def set_data_handler(self, handler: Callable[[SpeedCadenceData], None]) -> None:
        self._handler = handler

    def set_effort(self, fraction: float) -> None:
        """Set effort level (0.0-1.0) to control simulated speed/cadence."""
        self._effort = max(0.0, min(1.0, fraction))

    async def start_notifications(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._generate_loop())

    async def stop_notifications(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _generate_loop(self) -> None:
        try:
            while True:
                # Speed 2-12 m/s based on effort
                speed = 2.0 + self._effort * 10.0
                noise = random.gauss(0, speed * 0.03)
                speed = max(0.5, speed + noise)

                # Cadence 50-100 rpm based on effort
                cadence = int(50 + self._effort * 50)
                cadence += random.randint(-2, 2)
                cadence = max(30, cadence)

                # Accumulate revolutions (1Hz = 1 second of travel)
                wheel_revs_this_tick = speed / self._wheel_circumference
                self._cumulative_wheel_revs += int(round(wheel_revs_this_tick))
                crank_revs_this_tick = cadence / 60.0
                self._cumulative_crank_revs += int(round(crank_revs_this_tick))

                data = SpeedCadenceData(
                    wheel_speed=speed,
                    cadence=cadence,
                    cumulative_wheel_revs=self._cumulative_wheel_revs,
                    cumulative_crank_revs=self._cumulative_crank_revs,
                )
                if self._handler:
                    self._handler(data)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise


class SimulatedPowerMeter:
    """Simulated power meter for testing classic trainer setups.

    Generates power and cadence based on an effort fraction and FTP.
    """

    def __init__(self, ftp: int = 200):
        self._ftp = ftp
        self._connected = False
        self._handler: Optional[Callable[[PowerMeterData], None]] = None
        self._task: Optional[asyncio.Task] = None
        self._effort: float = 0.5

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        await self.stop_notifications()
        self._connected = False

    def set_data_handler(self, handler: Callable[[PowerMeterData], None]) -> None:
        self._handler = handler

    def set_effort(self, fraction: float) -> None:
        """Set effort level (0.0-1.0) to control simulated power."""
        self._effort = max(0.0, min(1.0, fraction))

    async def start_notifications(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._generate_loop())

    async def stop_notifications(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _generate_loop(self) -> None:
        try:
            while True:
                base_power = self._ftp * self._effort
                noise = random.gauss(0, base_power * 0.05) if base_power > 0 else 0
                power = max(0, int(base_power + noise))

                # Cadence loosely correlated with effort
                cadence = int(70 + self._effort * 20)
                cadence += random.randint(-3, 3)
                cadence = max(30, cadence)

                data = PowerMeterData(
                    instant_power=power,
                    cadence=cadence,
                )
                if self._handler:
                    self._handler(data)
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
