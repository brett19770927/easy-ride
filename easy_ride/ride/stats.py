from __future__ import annotations

from dataclasses import dataclass, field

from easy_ride.models import RideStats


@dataclass
class StatsCollector:
    """Collects running ride statistics from samples."""

    _speeds: list[float] = field(default_factory=list)
    _powers: list[int] = field(default_factory=list)
    _cadences: list[int] = field(default_factory=list)
    _heart_rates: list[int] = field(default_factory=list)
    _max_speed: float = 0.0
    _max_power: int = 0
    _distance: float = 0.0
    _total_ascent: float = 0.0
    _last_elevation: float | None = None
    _start_time: float | None = None
    _last_time: float | None = None

    def record(
        self,
        timestamp: float,
        speed: float,
        power: int,
        cadence: int,
        heart_rate: int,
        distance: float,
        elevation: float,
    ) -> None:
        if self._start_time is None:
            self._start_time = timestamp
        self._last_time = timestamp

        self._speeds.append(speed)
        self._powers.append(power)
        if cadence > 0:
            self._cadences.append(cadence)
        if heart_rate > 0:
            self._heart_rates.append(heart_rate)

        self._max_speed = max(self._max_speed, speed)
        self._max_power = max(self._max_power, power)
        self._distance = distance

        if self._last_elevation is not None and elevation > self._last_elevation:
            self._total_ascent += elevation - self._last_elevation
        self._last_elevation = elevation

    @property
    def sample_count(self) -> int:
        return len(self._speeds)

    @property
    def duration(self) -> float:
        if self._start_time is None or self._last_time is None:
            return 0.0
        return self._last_time - self._start_time

    def snapshot(self) -> RideStats:
        """Return current stats as a RideStats instance."""
        n_speeds = len(self._speeds)
        n_powers = len(self._powers)
        n_cadences = len(self._cadences)
        n_hrs = len(self._heart_rates)
        return RideStats(
            duration=self.duration,
            distance=self._distance,
            avg_speed=sum(self._speeds) / n_speeds if n_speeds else 0.0,
            max_speed=self._max_speed,
            avg_power=int(sum(self._powers) / n_powers) if n_powers else 0,
            max_power=self._max_power,
            avg_cadence=int(sum(self._cadences) / n_cadences) if n_cadences else 0,
            avg_heart_rate=int(sum(self._heart_rates) / n_hrs) if n_hrs else 0,
            total_ascent=self._total_ascent,
        )
