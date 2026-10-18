from __future__ import annotations

import asyncio

import pytest

from easy_ride.ble.device_types import (
    PowerMeterData,
    PowerMeterDevice,
    SpeedCadenceData,
    SpeedCadenceSensor,
)
from easy_ride.ble.simulator import SimulatedPowerMeter, SimulatedSpeedCadenceSensor


class TestSimulatedSpeedCadenceSensor:
    def test_implements_protocol(self):
        sensor = SimulatedSpeedCadenceSensor()
        assert isinstance(sensor, SpeedCadenceSensor)

    async def test_connect_disconnect(self):
        sensor = SimulatedSpeedCadenceSensor()
        assert not sensor.is_connected
        await sensor.connect()
        assert sensor.is_connected
        await sensor.disconnect()
        assert not sensor.is_connected

    async def test_generates_data(self):
        sensor = SimulatedSpeedCadenceSensor()
        await sensor.connect()
        received = []
        sensor.set_data_handler(lambda d: received.append(d))
        await sensor.start_notifications()
        await asyncio.sleep(1.5)
        await sensor.stop_notifications()
        await sensor.disconnect()
        assert len(received) >= 1
        data = received[0]
        assert isinstance(data, SpeedCadenceData)
        assert data.wheel_speed > 0
        assert data.cadence > 0
        assert data.cumulative_wheel_revs > 0

    async def test_effort_affects_speed(self):
        sensor = SimulatedSpeedCadenceSensor()
        await sensor.connect()

        low_speeds = []
        sensor.set_effort(0.1)
        sensor.set_data_handler(lambda d: low_speeds.append(d.wheel_speed))
        await sensor.start_notifications()
        await asyncio.sleep(2.5)
        await sensor.stop_notifications()

        high_speeds = []
        sensor.set_effort(0.9)
        sensor.set_data_handler(lambda d: high_speeds.append(d.wheel_speed))
        await sensor.start_notifications()
        await asyncio.sleep(2.5)
        await sensor.stop_notifications()
        await sensor.disconnect()

        avg_low = sum(low_speeds) / len(low_speeds)
        avg_high = sum(high_speeds) / len(high_speeds)
        assert avg_high > avg_low * 1.5

    async def test_cumulative_revs_increase(self):
        sensor = SimulatedSpeedCadenceSensor()
        await sensor.connect()
        received = []
        sensor.set_data_handler(lambda d: received.append(d))
        await sensor.start_notifications()
        await asyncio.sleep(2.5)
        await sensor.stop_notifications()
        await sensor.disconnect()
        assert len(received) >= 2
        for i in range(1, len(received)):
            assert received[i].cumulative_wheel_revs >= received[i - 1].cumulative_wheel_revs


class TestSimulatedPowerMeter:
    def test_implements_protocol(self):
        pm = SimulatedPowerMeter()
        assert isinstance(pm, PowerMeterDevice)

    async def test_connect_disconnect(self):
        pm = SimulatedPowerMeter()
        assert not pm.is_connected
        await pm.connect()
        assert pm.is_connected
        await pm.disconnect()
        assert not pm.is_connected

    async def test_generates_data(self):
        pm = SimulatedPowerMeter(ftp=200)
        await pm.connect()
        received = []
        pm.set_data_handler(lambda d: received.append(d))
        await pm.start_notifications()
        await asyncio.sleep(1.5)
        await pm.stop_notifications()
        await pm.disconnect()
        assert len(received) >= 1
        data = received[0]
        assert isinstance(data, PowerMeterData)
        assert data.instant_power > 0
        assert data.cadence > 0

    async def test_effort_affects_power(self):
        pm = SimulatedPowerMeter(ftp=200)
        await pm.connect()

        low_powers = []
        pm.set_effort(0.2)
        pm.set_data_handler(lambda d: low_powers.append(d.instant_power))
        await pm.start_notifications()
        await asyncio.sleep(2.5)
        await pm.stop_notifications()

        high_powers = []
        pm.set_effort(0.9)
        pm.set_data_handler(lambda d: high_powers.append(d.instant_power))
        await pm.start_notifications()
        await asyncio.sleep(2.5)
        await pm.stop_notifications()
        await pm.disconnect()

        avg_low = sum(low_powers) / len(low_powers)
        avg_high = sum(high_powers) / len(high_powers)
        assert avg_high > avg_low * 2
