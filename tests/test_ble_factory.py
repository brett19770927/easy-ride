from __future__ import annotations

import pytest

from easy_ride.ble.classic_adapter import ClassicTrainerAdapter
from easy_ride.ble.factory import build_devices_from_profile, validate_profile
from easy_ride.ble.hrm import BLEHeartRateMonitor
from easy_ride.ble.power_meter import BLEPowerMeter
from easy_ride.ble.speed_cadence import BLESpeedCadenceSensor
from easy_ride.ble.trainer import FTMSTrainer
from easy_ride.exceptions import ProfileValidationError
from easy_ride.models import TrainerProfile, TrainerType


def _make_profile(**overrides) -> TrainerProfile:
    defaults = dict(
        id="test-id",
        name="Test Profile",
        trainer_type=TrainerType.SMART,
        trainer_address="AA:BB:CC:DD:EE:FF",
    )
    defaults.update(overrides)
    return TrainerProfile(**defaults)


class TestValidateProfile:
    def test_smart_requires_trainer_address(self):
        profile = _make_profile(trainer_type=TrainerType.SMART, trainer_address=None)
        with pytest.raises(ProfileValidationError, match="trainer_address"):
            validate_profile(profile)

    def test_smart_valid(self):
        profile = _make_profile(trainer_type=TrainerType.SMART)
        validate_profile(profile)  # should not raise

    def test_classic_requires_speed_sensor_address(self):
        profile = _make_profile(
            trainer_type=TrainerType.CLASSIC,
            trainer_address=None,
            speed_sensor_address=None,
        )
        with pytest.raises(ProfileValidationError, match="speed_sensor_address"):
            validate_profile(profile)

    def test_classic_valid(self):
        profile = _make_profile(
            trainer_type=TrainerType.CLASSIC,
            speed_sensor_address="11:22:33:44:55:66",
        )
        validate_profile(profile)

    def test_power_meter_only_requires_power_meter_address(self):
        profile = _make_profile(
            trainer_type=TrainerType.POWER_METER_ONLY,
            trainer_address=None,
            power_meter_address=None,
        )
        with pytest.raises(ProfileValidationError, match="power_meter_address"):
            validate_profile(profile)

    def test_power_meter_only_valid(self):
        profile = _make_profile(
            trainer_type=TrainerType.POWER_METER_ONLY,
            power_meter_address="11:22:33:44:55:66",
        )
        validate_profile(profile)


class TestBuildDevicesFromProfile:
    def test_smart_creates_ftms_trainer(self):
        profile = _make_profile(trainer_type=TrainerType.SMART)
        trainer, hrm = build_devices_from_profile(profile)
        assert isinstance(trainer, FTMSTrainer)
        assert hrm is None

    def test_smart_with_hrm(self):
        profile = _make_profile(
            trainer_type=TrainerType.SMART,
            hrm_address="11:22:33:44:55:66",
        )
        trainer, hrm = build_devices_from_profile(profile)
        assert isinstance(trainer, FTMSTrainer)
        assert isinstance(hrm, BLEHeartRateMonitor)

    def test_classic_creates_adapter_with_speed_sensor(self):
        profile = _make_profile(
            trainer_type=TrainerType.CLASSIC,
            speed_sensor_address="11:22:33:44:55:66",
        )
        trainer, hrm = build_devices_from_profile(profile)
        assert isinstance(trainer, ClassicTrainerAdapter)
        assert trainer._speed_sensor is not None
        assert isinstance(trainer._speed_sensor, BLESpeedCadenceSensor)
        assert trainer._power_meter is None
        assert hrm is None

    def test_classic_with_power_meter(self):
        profile = _make_profile(
            trainer_type=TrainerType.CLASSIC,
            speed_sensor_address="11:22:33:44:55:66",
            power_meter_address="AA:BB:CC:DD:EE:01",
        )
        trainer, hrm = build_devices_from_profile(profile)
        assert isinstance(trainer, ClassicTrainerAdapter)
        assert isinstance(trainer._power_meter, BLEPowerMeter)

    def test_classic_passes_wheel_circumference(self):
        profile = _make_profile(
            trainer_type=TrainerType.CLASSIC,
            speed_sensor_address="11:22:33:44:55:66",
            wheel_circumference=2.200,
        )
        trainer, _ = build_devices_from_profile(profile)
        assert trainer._speed_sensor._wheel_circumference == 2.200

    def test_classic_passes_resistance_factor(self):
        profile = _make_profile(
            trainer_type=TrainerType.CLASSIC,
            speed_sensor_address="11:22:33:44:55:66",
            resistance_factor=25.0,
        )
        trainer, _ = build_devices_from_profile(profile)
        assert trainer._resistance_factor == 25.0

    def test_power_meter_only_creates_adapter(self):
        profile = _make_profile(
            trainer_type=TrainerType.POWER_METER_ONLY,
            power_meter_address="11:22:33:44:55:66",
        )
        trainer, hrm = build_devices_from_profile(profile)
        assert isinstance(trainer, ClassicTrainerAdapter)
        assert trainer._speed_sensor is None
        assert isinstance(trainer._power_meter, BLEPowerMeter)
        assert hrm is None

    def test_power_meter_only_with_hrm(self):
        profile = _make_profile(
            trainer_type=TrainerType.POWER_METER_ONLY,
            power_meter_address="11:22:33:44:55:66",
            hrm_address="AA:BB:CC:DD:EE:02",
        )
        trainer, hrm = build_devices_from_profile(profile)
        assert isinstance(trainer, ClassicTrainerAdapter)
        assert isinstance(hrm, BLEHeartRateMonitor)

    def test_invalid_profile_raises(self):
        profile = _make_profile(trainer_type=TrainerType.SMART, trainer_address=None)
        with pytest.raises(ProfileValidationError):
            build_devices_from_profile(profile)
