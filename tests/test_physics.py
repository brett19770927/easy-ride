from __future__ import annotations

import pytest

from easy_ride.ride.physics import (
    effort_fraction,
    ftms_grade_from_gradient,
    required_power,
    speed_from_power,
)


class TestRequiredPower:
    def test_flat_zero_speed(self):
        assert required_power(0.0, 0.0, 75.0) == 0.0

    def test_flat_nonzero_speed(self):
        power = required_power(0.0, 8.0, 75.0)  # ~29 km/h on flat
        assert 100 < power < 400

    def test_uphill_more_than_flat(self):
        flat = required_power(0.0, 5.0, 75.0)
        uphill = required_power(0.05, 5.0, 75.0)
        assert uphill > flat

    def test_steep_climb_high_power(self):
        power = required_power(0.10, 3.0, 75.0)  # 10% at ~11 km/h
        assert power > 200

    def test_downhill_less_than_flat(self):
        flat = required_power(0.0, 5.0, 75.0)
        downhill = required_power(-0.05, 5.0, 75.0)
        assert downhill < flat

    def test_never_negative(self):
        power = required_power(-0.10, 2.0, 75.0)
        assert power >= 0.0

    def test_heavier_rider_more_power(self):
        light = required_power(0.03, 5.0, 60.0)
        heavy = required_power(0.03, 5.0, 90.0)
        assert heavy > light


class TestSpeedFromPower:
    def test_zero_power_minimal_speed(self):
        speed = speed_from_power(0.0, 0.0, 75.0)
        assert speed < 1.0

    def test_moderate_power_flat(self):
        speed = speed_from_power(200.0, 0.0, 75.0)
        assert 7.0 < speed < 12.0  # ~25-40 km/h

    def test_uphill_slower(self):
        flat_speed = speed_from_power(200.0, 0.0, 75.0)
        uphill_speed = speed_from_power(200.0, 0.05, 75.0)
        assert uphill_speed < flat_speed

    def test_more_power_faster(self):
        slow = speed_from_power(100.0, 0.0, 75.0)
        fast = speed_from_power(300.0, 0.0, 75.0)
        assert fast > slow

    def test_inverse_of_required_power(self):
        """speed_from_power and required_power should be approximate inverses."""
        target_speed = 7.0
        gradient = 0.03
        mass = 75.0
        power = required_power(gradient, target_speed, mass)
        recovered_speed = speed_from_power(power, gradient, mass)
        assert recovered_speed == pytest.approx(target_speed, rel=0.05)


class TestFTMSGrade:
    def test_zero(self):
        assert ftms_grade_from_gradient(0.0) == 0

    def test_ten_percent(self):
        assert ftms_grade_from_gradient(10.0) == 1000

    def test_negative(self):
        assert ftms_grade_from_gradient(-5.0) == -500

    def test_clamp_upper(self):
        assert ftms_grade_from_gradient(50.0) == 4000

    def test_clamp_lower(self):
        assert ftms_grade_from_gradient(-50.0) == -4000


class TestEffortFraction:
    def test_zero_power(self):
        assert effort_fraction(0.0, 200) == 0.0

    def test_ftp_power(self):
        assert effort_fraction(200.0, 200) == pytest.approx(1.0)

    def test_half_ftp(self):
        assert effort_fraction(100.0, 200) == pytest.approx(0.5)

    def test_above_ftp(self):
        assert effort_fraction(300.0, 200) == pytest.approx(1.5)

    def test_zero_ftp(self):
        assert effort_fraction(100.0, 0) == 0.0
