from __future__ import annotations

import pytest

from easy_ride.ride.stats import StatsCollector


class TestStatsCollector:
    def test_empty_snapshot(self):
        sc = StatsCollector()
        stats = sc.snapshot()
        assert stats.duration == 0.0
        assert stats.distance == 0.0
        assert stats.avg_speed == 0.0
        assert stats.max_speed == 0.0
        assert stats.avg_power == 0
        assert stats.max_power == 0

    def test_single_sample(self):
        sc = StatsCollector()
        sc.record(
            timestamp=100.0, speed=5.0, power=150, cadence=85,
            heart_rate=130, distance=10.0, elevation=100.0,
        )
        stats = sc.snapshot()
        assert stats.distance == 10.0
        assert stats.avg_speed == 5.0
        assert stats.max_speed == 5.0
        assert stats.avg_power == 150
        assert stats.max_power == 150
        assert stats.avg_cadence == 85
        assert stats.avg_heart_rate == 130
        assert sc.sample_count == 1

    def test_multiple_samples_averages(self):
        sc = StatsCollector()
        sc.record(100.0, 4.0, 100, 80, 120, 5.0, 100.0)
        sc.record(101.0, 6.0, 200, 90, 140, 15.0, 105.0)
        stats = sc.snapshot()
        assert stats.avg_speed == pytest.approx(5.0)
        assert stats.avg_power == 150
        assert stats.max_speed == 6.0
        assert stats.max_power == 200
        assert stats.duration == pytest.approx(1.0)

    def test_max_tracking(self):
        sc = StatsCollector()
        sc.record(100.0, 3.0, 100, 80, 120, 5.0, 100.0)
        sc.record(101.0, 8.0, 300, 90, 150, 15.0, 105.0)
        sc.record(102.0, 5.0, 150, 85, 135, 25.0, 103.0)
        stats = sc.snapshot()
        assert stats.max_speed == 8.0
        assert stats.max_power == 300

    def test_ascent_tracking(self):
        sc = StatsCollector()
        sc.record(100.0, 5.0, 150, 85, 130, 10.0, 100.0)
        sc.record(101.0, 5.0, 150, 85, 130, 20.0, 110.0)  # +10m
        sc.record(102.0, 5.0, 150, 85, 130, 30.0, 105.0)  # -5m (descent)
        sc.record(103.0, 5.0, 150, 85, 130, 40.0, 115.0)  # +10m
        stats = sc.snapshot()
        assert stats.total_ascent == pytest.approx(20.0)

    def test_zero_cadence_excluded_from_average(self):
        sc = StatsCollector()
        sc.record(100.0, 5.0, 150, 85, 130, 10.0, 100.0)
        sc.record(101.0, 5.0, 150, 0, 130, 20.0, 100.0)  # coasting
        stats = sc.snapshot()
        assert stats.avg_cadence == 85  # Only one sample counted

    def test_zero_hr_excluded_from_average(self):
        sc = StatsCollector()
        sc.record(100.0, 5.0, 150, 85, 130, 10.0, 100.0)
        sc.record(101.0, 5.0, 150, 85, 0, 20.0, 100.0)  # no contact
        stats = sc.snapshot()
        assert stats.avg_heart_rate == 130

    def test_duration_calculation(self):
        sc = StatsCollector()
        sc.record(1000.0, 5.0, 150, 85, 130, 10.0, 100.0)
        sc.record(1060.0, 5.0, 150, 85, 130, 310.0, 100.0)
        assert sc.duration == pytest.approx(60.0)
