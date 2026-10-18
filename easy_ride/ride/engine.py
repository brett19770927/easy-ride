from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Optional

from easy_ride.ble.device_types import HRMData, TrainerData, TrainerDevice, HRMDevice
from easy_ride.ble.simulator import SimulatedHRM
from easy_ride.exceptions import RideStateError
from easy_ride.models import Ride, RideSample, RideStatus, Route
from easy_ride.ride.physics import effort_fraction
from easy_ride.ride.stats import StatsCollector


class RideEngine:
    """State machine that runs a ride on a route with a trainer device.

    States: idle → active ↔ paused → completed/cancelled

    The engine runs a 1Hz main loop when active that:
    1. Drains device data
    2. Updates distance from trainer speed
    3. Finds current route point
    4. Sets trainer gradient
    5. Collects sample + updates stats
    6. Publishes to subscribers
    7. Auto-completes when distance >= route total
    """

    def __init__(
        self,
        route: Route,
        trainer: TrainerDevice,
        hrm: Optional[HRMDevice] = None,
        ftp: int = 200,
    ):
        self._route = route
        self._trainer = trainer
        self._hrm = hrm
        self._ftp = ftp

        self._ride_id = str(uuid.uuid4())
        self._status = RideStatus.ACTIVE
        self._started_at: Optional[str] = None

        self._stats = StatsCollector()
        self._samples: list[RideSample] = []
        self._subscribers: list[Callable[[dict[str, Any]], None]] = []

        # Latest device data
        self._trainer_data: Optional[TrainerData] = None
        self._hrm_data: Optional[HRMData] = None
        self._distance: float = 0.0
        self._current_point_idx: int = 0

        self._task: Optional[asyncio.Task] = None

    @property
    def ride_id(self) -> str:
        return self._ride_id

    @property
    def status(self) -> RideStatus:
        return self._status

    @property
    def samples(self) -> list[RideSample]:
        return list(self._samples)

    @property
    def stats(self) -> StatsCollector:
        return self._stats

    @property
    def current_point_idx(self) -> int:
        return self._current_point_idx

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers = [s for s in self._subscribers if s is not callback]

    def _publish(self, event: dict[str, Any]) -> None:
        for sub in self._subscribers:
            sub(event)

    def _on_trainer_data(self, data: TrainerData) -> None:
        self._trainer_data = data

    def _on_hrm_data(self, data: HRMData) -> None:
        self._hrm_data = data

    def _find_point_idx(self, distance: float) -> int:
        """Find the route point index for a given cumulative distance."""
        points = self._route.points
        for i in range(len(points) - 1):
            if distance < points[i + 1].cumulative_distance:
                return i
        return len(points) - 1

    def _current_gradient(self) -> float:
        """Get the gradient at the current position (percent)."""
        idx = self._current_point_idx
        if idx < len(self._route.points):
            return self._route.points[idx].gradient_smoothed
        return 0.0

    def _current_elevation(self) -> float:
        """Get the elevation at the current position."""
        idx = self._current_point_idx
        if idx < len(self._route.points):
            return self._route.points[idx].elevation_smoothed
        return 0.0

    async def start(self) -> Ride:
        """Start the ride — connect devices and begin the main loop."""
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        self._trainer.set_data_handler(self._on_trainer_data)
        await self._trainer.start_notifications()

        if self._hrm is not None:
            self._hrm.set_data_handler(self._on_hrm_data)
            await self._hrm.start_notifications()

        self._task = asyncio.create_task(self._main_loop())
        return self._to_ride()

    async def pause(self) -> Ride:
        if self._status != RideStatus.ACTIVE:
            raise RideStateError(self._ride_id, self._status.value, "paused")
        self._status = RideStatus.PAUSED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        return self._to_ride()

    async def resume(self) -> Ride:
        if self._status != RideStatus.PAUSED:
            raise RideStateError(self._ride_id, self._status.value, "active")
        self._status = RideStatus.ACTIVE
        self._task = asyncio.create_task(self._main_loop())
        return self._to_ride()

    async def stop(self) -> Ride:
        if self._status not in (RideStatus.ACTIVE, RideStatus.PAUSED):
            raise RideStateError(self._ride_id, self._status.value, "completed")
        self._status = RideStatus.COMPLETED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._trainer.stop_notifications()
        if self._hrm:
            await self._hrm.stop_notifications()
        return self._to_ride()

    def _to_ride(self) -> Ride:
        return Ride(
            id=self._ride_id,
            route_id=self._route.id,
            status=self._status,
            started_at=self._started_at or "",
            finished_at=(
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if self._status in (RideStatus.COMPLETED, RideStatus.CANCELLED)
                else None
            ),
            stats=self._stats.snapshot() if self._stats.sample_count > 0 else None,
            samples=list(self._samples),
        )

    async def _main_loop(self) -> None:
        try:
            total_distance = self._route.stats.total_distance
            while True:
                now = time.time()

                # Process trainer data
                td = self._trainer_data
                speed = td.instant_speed if td else 0.0
                power = td.instant_power if td else 0
                cadence = td.instant_cadence if td else 0
                if td:
                    self._distance = td.distance

                # Process HRM data
                heart_rate = self._hrm_data.bpm if self._hrm_data else 0

                # Update HRM effort for simulator
                if self._hrm and isinstance(self._hrm, SimulatedHRM):
                    ef = effort_fraction(float(power), self._ftp)
                    self._hrm.set_effort(ef)

                # Find current route position
                self._current_point_idx = self._find_point_idx(self._distance)
                gradient = self._current_gradient()
                elevation = self._current_elevation()

                # Set trainer gradient
                await self._trainer.set_target_gradient(gradient)

                # Record sample
                sample = RideSample(
                    timestamp=now,
                    distance=self._distance,
                    speed=speed,
                    power=power,
                    cadence=cadence,
                    heart_rate=heart_rate,
                    route_point_idx=self._current_point_idx,
                )
                self._samples.append(sample)

                # Update stats
                self._stats.record(
                    timestamp=now,
                    speed=speed,
                    power=power,
                    cadence=cadence,
                    heart_rate=heart_rate,
                    distance=self._distance,
                    elevation=elevation,
                )

                # Publish event
                snapshot = self._stats.snapshot()
                event = {
                    "type": "sample",
                    "ride_id": self._ride_id,
                    "sample": {
                        "timestamp": now,
                        "distance": self._distance,
                        "speed": speed,
                        "power": power,
                        "cadence": cadence,
                        "heart_rate": heart_rate,
                        "route_point_idx": self._current_point_idx,
                    },
                    "stats": {
                        "duration": snapshot.duration,
                        "distance": snapshot.distance,
                        "avg_speed": snapshot.avg_speed,
                        "max_speed": snapshot.max_speed,
                        "avg_power": snapshot.avg_power,
                        "max_power": snapshot.max_power,
                        "avg_cadence": snapshot.avg_cadence,
                        "avg_heart_rate": snapshot.avg_heart_rate,
                    },
                }
                self._publish(event)

                # Auto-complete check
                if total_distance > 0 and self._distance >= total_distance:
                    self._status = RideStatus.COMPLETED
                    self._publish({
                        "type": "completed",
                        "ride_id": self._ride_id,
                    })
                    await self._trainer.stop_notifications()
                    if self._hrm:
                        await self._hrm.stop_notifications()
                    return

                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise
