from __future__ import annotations

import asyncio

import pytest

from easy_ride.ble.device_types import HRMData, TrainerData, TrainerDevice, HRMDevice
from easy_ride.ble.simulator import SimulatedHRM, SimulatedTrainer


class TestSimulatedTrainer:
    def test_implements_protocol(self):
        trainer = SimulatedTrainer()
        assert isinstance(trainer, TrainerDevice)

    async def test_connect_disconnect(self):
        trainer = SimulatedTrainer()
        assert not trainer.is_connected
        await trainer.connect()
        assert trainer.is_connected
        await trainer.disconnect()
        assert not trainer.is_connected

    async def test_generates_data(self):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        received = []
        trainer.set_data_handler(lambda d: received.append(d))
        await trainer.start_notifications()
        await asyncio.sleep(1.5)  # Should get at least 1 sample
        await trainer.stop_notifications()
        await trainer.disconnect()
        assert len(received) >= 1
        data = received[0]
        assert isinstance(data, TrainerData)
        assert data.instant_speed > 0
        assert data.instant_power > 0
        assert data.instant_cadence > 0
        assert data.distance > 0

    async def test_gradient_affects_power(self):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()

        flat_powers = []
        trainer.set_data_handler(lambda d: flat_powers.append(d.instant_power))
        await trainer.set_target_gradient(0.0)
        await trainer.start_notifications()
        await asyncio.sleep(3.5)
        await trainer.stop_notifications()

        hill_powers = []
        trainer.set_data_handler(lambda d: hill_powers.append(d.instant_power))
        await trainer.set_target_gradient(10.0)
        await trainer.start_notifications()
        await asyncio.sleep(3.5)
        await trainer.stop_notifications()

        await trainer.disconnect()

        avg_flat = sum(flat_powers) / len(flat_powers) if flat_powers else 0
        avg_hill = sum(hill_powers) / len(hill_powers) if hill_powers else 0
        assert avg_hill > avg_flat * 1.3  # Hill should be notably higher

    async def test_target_power_mode(self):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        await trainer.set_target_power(250)
        received = []
        trainer.set_data_handler(lambda d: received.append(d.instant_power))
        await trainer.start_notifications()
        await asyncio.sleep(2.5)
        await trainer.stop_notifications()
        await trainer.disconnect()
        avg = sum(received) / len(received) if received else 0
        assert 220 < avg < 280  # Should be close to 250

    async def test_cumulative_distance(self):
        trainer = SimulatedTrainer(ftp=200, weight=75.0)
        await trainer.connect()
        received = []
        trainer.set_data_handler(lambda d: received.append(d.distance))
        await trainer.start_notifications()
        await asyncio.sleep(2.5)
        await trainer.stop_notifications()
        await trainer.disconnect()
        assert len(received) >= 2
        # Distance should increase monotonically
        for i in range(1, len(received)):
            assert received[i] > received[i - 1]


class TestSimulatedHRM:
    def test_implements_protocol(self):
        hrm = SimulatedHRM()
        assert isinstance(hrm, HRMDevice)

    async def test_connect_disconnect(self):
        hrm = SimulatedHRM()
        assert not hrm.is_connected
        await hrm.connect()
        assert hrm.is_connected
        await hrm.disconnect()
        assert not hrm.is_connected

    async def test_generates_data(self):
        hrm = SimulatedHRM(resting_hr=65, max_hr=185)
        await hrm.connect()
        received = []
        hrm.set_data_handler(lambda d: received.append(d))
        await hrm.start_notifications()
        await asyncio.sleep(1.5)
        await hrm.stop_notifications()
        await hrm.disconnect()
        assert len(received) >= 1
        data = received[0]
        assert isinstance(data, HRMData)
        assert data.sensor_contact is True
        assert 50 <= data.bpm <= 200

    async def test_effort_raises_hr(self):
        hrm = SimulatedHRM(resting_hr=65, max_hr=185)
        await hrm.connect()

        # Rest for a moment
        rest_bpms = []
        hrm.set_data_handler(lambda d: rest_bpms.append(d.bpm))
        hrm.set_effort(0.0)
        await hrm.start_notifications()
        await asyncio.sleep(2.5)
        await hrm.stop_notifications()

        # Now set high effort
        effort_bpms = []
        hrm.set_data_handler(lambda d: effort_bpms.append(d.bpm))
        hrm.set_effort(1.0)
        await hrm.start_notifications()
        await asyncio.sleep(5.5)  # Give time for HR to drift up
        await hrm.stop_notifications()

        await hrm.disconnect()

        avg_rest = sum(rest_bpms) / len(rest_bpms) if rest_bpms else 0
        avg_effort = sum(effort_bpms) / len(effort_bpms) if effort_bpms else 0
        assert avg_effort > avg_rest

    async def test_hr_stays_in_bounds(self):
        hrm = SimulatedHRM(resting_hr=65, max_hr=185)
        await hrm.connect()
        received = []
        hrm.set_data_handler(lambda d: received.append(d.bpm))
        hrm.set_effort(1.5)  # Above FTP
        await hrm.start_notifications()
        await asyncio.sleep(3.5)
        await hrm.stop_notifications()
        await hrm.disconnect()
        for bpm in received:
            assert 50 <= bpm <= 185
