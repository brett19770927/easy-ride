from __future__ import annotations

from easy_ride.ble.device_types import DeviceType
from easy_ride.ble.scanner import (
    CPS_UUID,
    CSC_UUID,
    FTMS_UUID,
    HRS_UUID,
    _classify_device,
)


class TestClassifyDevice:
    def test_ftms_classified_as_trainer(self):
        assert _classify_device([FTMS_UUID]) == DeviceType.TRAINER

    def test_ftms_with_cps_still_trainer(self):
        """FTMS takes priority — it's a smart trainer even if CPS present."""
        assert _classify_device([FTMS_UUID, CPS_UUID]) == DeviceType.TRAINER

    def test_cps_without_ftms_is_power_meter(self):
        assert _classify_device([CPS_UUID]) == DeviceType.POWER_METER

    def test_cps_takes_priority_over_csc(self):
        """Some power meters advertise both CPS and CSC."""
        assert _classify_device([CPS_UUID, CSC_UUID]) == DeviceType.POWER_METER

    def test_csc_only_is_speed_cadence(self):
        assert _classify_device([CSC_UUID]) == DeviceType.SPEED_CADENCE

    def test_hrs_is_hrm(self):
        assert _classify_device([HRS_UUID]) == DeviceType.HRM

    def test_empty_uuids_is_unknown(self):
        assert _classify_device([]) == DeviceType.UNKNOWN

    def test_unrecognised_uuid_is_unknown(self):
        assert _classify_device(["0000abcd-0000-1000-8000-00805f9b34fb"]) == DeviceType.UNKNOWN

    def test_case_insensitive(self):
        assert _classify_device([FTMS_UUID.upper()]) == DeviceType.TRAINER

    def test_csc_with_hrs(self):
        """CSC takes priority over HRS when both present."""
        assert _classify_device([CSC_UUID, HRS_UUID]) == DeviceType.SPEED_CADENCE
