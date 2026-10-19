from __future__ import annotations

from typing import Optional

from easy_ride.ble.classic_adapter import ClassicTrainerAdapter
from easy_ride.ble.hrm import BLEHeartRateMonitor
from easy_ride.ble.power_meter import BLEPowerMeter
from easy_ride.ble.speed_cadence import BLESpeedCadenceSensor
from easy_ride.ble.trainer import FTMSTrainer
from easy_ride.exceptions import ProfileValidationError
from easy_ride.models import TrainerProfile, TrainerType


def validate_profile(profile: TrainerProfile) -> None:
    """Validate that a profile has the required device addresses for its type."""
    if profile.trainer_type == TrainerType.SMART:
        if not profile.trainer_address:
            raise ProfileValidationError(
                "SMART profile requires a trainer_address"
            )
    elif profile.trainer_type == TrainerType.CLASSIC:
        if not profile.speed_sensor_address:
            raise ProfileValidationError(
                "CLASSIC profile requires a speed_sensor_address"
            )
    elif profile.trainer_type == TrainerType.POWER_METER_ONLY:
        if not profile.power_meter_address:
            raise ProfileValidationError(
                "POWER_METER_ONLY profile requires a power_meter_address"
            )


def build_devices_from_profile(
    profile: TrainerProfile,
) -> tuple:
    """Instantiate (but don't connect) BLE devices from a trainer profile.

    Returns (trainer_device, hrm_device_or_none).
    """
    validate_profile(profile)

    hrm: Optional[BLEHeartRateMonitor] = None
    if profile.hrm_address:
        hrm = BLEHeartRateMonitor(profile.hrm_address)

    if profile.trainer_type == TrainerType.SMART:
        trainer = FTMSTrainer(profile.trainer_address)
        return trainer, hrm

    if profile.trainer_type == TrainerType.CLASSIC:
        speed_sensor = BLESpeedCadenceSensor(
            profile.speed_sensor_address,
            wheel_circumference=profile.wheel_circumference,
        )
        power_meter = None
        if profile.power_meter_address:
            power_meter = BLEPowerMeter(profile.power_meter_address)
        trainer = ClassicTrainerAdapter(
            speed_sensor=speed_sensor,
            power_meter=power_meter,
            resistance_factor=profile.resistance_factor,
        )
        return trainer, hrm

    if profile.trainer_type == TrainerType.POWER_METER_ONLY:
        power_meter = BLEPowerMeter(profile.power_meter_address)
        trainer = ClassicTrainerAdapter(
            power_meter=power_meter,
            resistance_factor=profile.resistance_factor,
        )
        return trainer, hrm

    raise ProfileValidationError(f"Unknown trainer type: {profile.trainer_type}")
