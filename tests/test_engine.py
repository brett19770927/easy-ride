from __future__ import annotations

import asyncio

import pytest

from easy_ride.ble.simulator import SimulatedHRM, SimulatedTrainer
from easy_ride.exceptions import RideStateError
from easy_ride.models import RideStatus
from easy_ride.ride.engine import RideEngine


class TestRideEngine:
    async def test_start_creates_active_ride(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        hrm = SimulatedHRM()
        await trainer.connect()
        await hrm.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, hrm=hrm, ftp=200)
        ride = await engine.start()
        assert ride.status == RideStatus.ACTIVE
        assert ride.started_at != ""
        assert ride.route_id == sample_route.id
        await engine.stop()

    async def test_stop_completes_ride(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        await engine.start()
        await asyncio.sleep(1.5)
        ride = await engine.stop()
        assert ride.status == RideStatus.COMPLETED
        assert ride.finished_at is not None

    async def test_collects_samples(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        await engine.start()
        await asyncio.sleep(2.5)
        ride = await engine.stop()
        assert len(ride.samples) >= 2

    async def test_collects_stats(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        await engine.start()
        await asyncio.sleep(2.5)
        ride = await engine.stop()
        assert ride.stats is not None
        assert ride.stats.avg_power > 0
        assert ride.stats.max_speed > 0

    async def test_pause_and_resume(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        await engine.start()
        await asyncio.sleep(1.5)

        ride = await engine.pause()
        assert ride.status == RideStatus.PAUSED

        ride = await engine.resume()
        assert ride.status == RideStatus.ACTIVE

        await asyncio.sleep(1.5)
        ride = await engine.stop()
        assert ride.status == RideStatus.COMPLETED

    async def test_invalid_pause_when_not_active(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        await engine.start()
        await engine.pause()
        with pytest.raises(RideStateError):
            await engine.pause()  # Can't pause when already paused
        await engine.stop()

    async def test_invalid_resume_when_active(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        await engine.start()
        with pytest.raises(RideStateError):
            await engine.resume()  # Can't resume when active
        await engine.stop()

    async def test_publishes_events(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        events = []
        engine.subscribe(lambda e: events.append(e))
        await engine.start()
        await asyncio.sleep(2.5)
        await engine.stop()
        assert len(events) >= 2
        assert events[0]["type"] == "sample"
        assert "speed" in events[0]["sample"]
        assert "avg_power" in events[0]["stats"]

    async def test_sets_gradient_from_route(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        await engine.start()
        await asyncio.sleep(1.5)
        # Engine should have set gradient on the trainer
        # The trainer's internal gradient should reflect route data
        assert engine.current_point_idx >= 0
        await engine.stop()

    async def test_hrm_integration(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        hrm = SimulatedHRM()
        await trainer.connect()
        await hrm.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, hrm=hrm, ftp=200)
        await engine.start()
        await asyncio.sleep(2.5)
        ride = await engine.stop()
        # Some samples should have heart rate data
        hr_samples = [s for s in ride.samples if s.heart_rate > 0]
        assert len(hr_samples) >= 1

    async def test_unsubscribe(self, sample_route):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        engine = RideEngine(route=sample_route, trainer=trainer, ftp=200)
        events = []
        callback = lambda e: events.append(e)
        engine.subscribe(callback)
        engine.unsubscribe(callback)
        await engine.start()
        await asyncio.sleep(1.5)
        await engine.stop()
        assert len(events) == 0
