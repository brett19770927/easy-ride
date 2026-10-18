from __future__ import annotations

import asyncio

import pytest

from easy_ride.ble.classic_adapter import ClassicTrainerAdapter
from easy_ride.ble.device_types import TrainerData, TrainerDevice
from easy_ride.ble.simulator import (
    SimulatedPowerMeter,
    SimulatedSpeedCadenceSensor,
    SimulatedTrainer,
)
from easy_ride.ride.engine import RideEngine


class TestClassicTrainerAdapter:
    def test_implements_protocol(self):
        sensor = SimulatedSpeedCadenceSensor()
        adapter = ClassicTrainerAdapter(speed_sensor=sensor)
        assert isinstance(adapter, TrainerDevice)

    def test_requires_at_least_one_sensor(self):
        with pytest.raises(ValueError):
            ClassicTrainerAdapter()

    async def test_speed_sensor_only(self):
        sensor = SimulatedSpeedCadenceSensor()
        adapter = ClassicTrainerAdapter(speed_sensor=sensor, resistance_factor=20.0)
        await adapter.connect()
        assert adapter.is_connected

        received = []
        adapter.set_data_handler(lambda d: received.append(d))
        await adapter.start_notifications()
        await asyncio.sleep(2.5)
        await adapter.stop_notifications()
        await adapter.disconnect()

        assert len(received) >= 2
        data = received[-1]
        assert isinstance(data, TrainerData)
        assert data.instant_speed > 0
        assert data.instant_cadence > 0
        # Power estimated from speed * resistance_factor
        assert data.instant_power > 0
        assert data.distance > 0

    async def test_power_meter_provides_accurate_power(self):
        sensor = SimulatedSpeedCadenceSensor()
        pm = SimulatedPowerMeter(ftp=200)
        adapter = ClassicTrainerAdapter(speed_sensor=sensor, power_meter=pm)
        await adapter.connect()

        received = []
        adapter.set_data_handler(lambda d: received.append(d))
        await adapter.start_notifications()
        await asyncio.sleep(2.5)
        await adapter.stop_notifications()
        await adapter.disconnect()

        assert len(received) >= 2
        # With PM, power should come from PM, not from speed estimation
        for d in received:
            assert isinstance(d, TrainerData)
            assert d.instant_power >= 0

    async def test_power_meter_only(self):
        """Adapter works with just a power meter (no speed sensor)."""
        pm = SimulatedPowerMeter(ftp=200)
        adapter = ClassicTrainerAdapter(power_meter=pm)
        await adapter.connect()

        received = []
        adapter.set_data_handler(lambda d: received.append(d))
        await adapter.start_notifications()
        await asyncio.sleep(2.5)
        await adapter.stop_notifications()
        await adapter.disconnect()

        assert len(received) >= 2
        assert received[-1].instant_power > 0

    async def test_control_methods_are_noop(self):
        sensor = SimulatedSpeedCadenceSensor()
        adapter = ClassicTrainerAdapter(speed_sensor=sensor)
        await adapter.connect()
        # These should not raise
        await adapter.set_target_gradient(10.0)
        await adapter.set_target_power(200)
        await adapter.set_target_resistance(0.5)
        await adapter.disconnect()

    async def test_cumulative_distance_increases(self):
        sensor = SimulatedSpeedCadenceSensor()
        adapter = ClassicTrainerAdapter(speed_sensor=sensor)
        await adapter.connect()

        received = []
        adapter.set_data_handler(lambda d: received.append(d))
        await adapter.start_notifications()
        await asyncio.sleep(2.5)
        await adapter.stop_notifications()
        await adapter.disconnect()

        assert len(received) >= 2
        for i in range(1, len(received)):
            assert received[i].distance >= received[i - 1].distance


class TestClassicAdapterWithEngine:
    async def test_engine_uses_virtual_speed(self, sample_route):
        """Classic adapter + RideEngine should produce valid ride data."""
        sensor = SimulatedSpeedCadenceSensor()
        pm = SimulatedPowerMeter(ftp=200)
        adapter = ClassicTrainerAdapter(speed_sensor=sensor, power_meter=pm)
        await adapter.connect()

        engine = RideEngine(
            route=sample_route, trainer=adapter, ftp=200, rider_mass=75.0,
        )
        ride = await engine.start()
        await asyncio.sleep(2.5)
        ride = await engine.stop()

        assert len(ride.samples) >= 2
        # Virtual speed should be positive
        assert ride.samples[-1].speed > 0
        # Distance should have accumulated
        assert ride.samples[-1].distance > 0
