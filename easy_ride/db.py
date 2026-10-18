from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from easy_ride.exceptions import (
    DatabaseError,
    ProfileNotFoundError,
    RideNotFoundError,
    RouteNotFoundError,
)
from easy_ride.models import (
    Ride,
    RideSample,
    RideStats,
    RideStatus,
    Route,
    RoutePoint,
    RouteStats,
    TrainerProfile,
    TrainerType,
    UserSettings,
)

SCHEMA_VERSION = 3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS routes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_filename TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    total_distance REAL NOT NULL DEFAULT 0,
    total_ascent REAL NOT NULL DEFAULT 0,
    total_descent REAL NOT NULL DEFAULT 0,
    min_elevation REAL NOT NULL DEFAULT 0,
    max_elevation REAL NOT NULL DEFAULT 0,
    max_gradient REAL NOT NULL DEFAULT 0,
    min_gradient REAL NOT NULL DEFAULT 0,
    point_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS route_points (
    route_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    elevation_raw REAL NOT NULL,
    elevation_smoothed REAL NOT NULL,
    cumulative_distance REAL NOT NULL,
    gradient_raw REAL NOT NULL,
    gradient_smoothed REAL NOT NULL,
    bearing REAL NOT NULL,
    PRIMARY KEY (route_id, idx),
    FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rides (
    id TEXT PRIMARY KEY,
    route_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    stats_json TEXT,
    FOREIGN KEY (route_id) REFERENCES routes(id)
);

CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ride_samples (
    ride_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    distance REAL NOT NULL,
    speed REAL NOT NULL,
    power INTEGER NOT NULL,
    cadence INTEGER NOT NULL,
    heart_rate INTEGER NOT NULL,
    route_point_idx INTEGER NOT NULL,
    PRIMARY KEY (ride_id, idx),
    FOREIGN KEY (ride_id) REFERENCES rides(id) ON DELETE CASCADE
);
"""


async def connect_db(db_path: Path) -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    db.row_factory = aiosqlite.Row
    return db


MIGRATION_V2 = """
CREATE TABLE IF NOT EXISTS ride_samples (
    ride_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    distance REAL NOT NULL,
    speed REAL NOT NULL,
    power INTEGER NOT NULL,
    cadence INTEGER NOT NULL,
    heart_rate INTEGER NOT NULL,
    route_point_idx INTEGER NOT NULL,
    PRIMARY KEY (ride_id, idx),
    FOREIGN KEY (ride_id) REFERENCES rides(id) ON DELETE CASCADE
);
"""

MIGRATION_V3 = """
CREATE TABLE IF NOT EXISTS trainer_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trainer_type TEXT NOT NULL,
    trainer_address TEXT,
    speed_sensor_address TEXT,
    cadence_sensor_address TEXT,
    power_meter_address TEXT,
    hrm_address TEXT,
    resistance_factor REAL NOT NULL DEFAULT 20.0,
    wheel_circumference REAL NOT NULL DEFAULT 2.105,
    is_default INTEGER NOT NULL DEFAULT 0
);
"""


async def init_db(db: aiosqlite.Connection) -> None:
    await db.executescript(SCHEMA_SQL)
    cursor = await db.execute("SELECT version FROM schema_version")
    row = await cursor.fetchone()
    if row is None:
        await db.execute(
            "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
        )
        await db.executescript(MIGRATION_V3)
    else:
        current = row[0] if isinstance(row[0], int) else row["version"]
        if current < 2:
            await db.executescript(MIGRATION_V2)
        if current < 3:
            await db.executescript(MIGRATION_V3)
        if current < SCHEMA_VERSION:
            await db.execute(
                "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
            )
    await db.commit()


async def insert_route(db: aiosqlite.Connection, route: Route) -> None:
    await db.execute(
        """INSERT INTO routes
           (id, name, source_filename, created_at,
            total_distance, total_ascent, total_descent,
            min_elevation, max_elevation, max_gradient, min_gradient, point_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            route.id, route.name, route.source_filename, route.created_at,
            route.stats.total_distance, route.stats.total_ascent,
            route.stats.total_descent, route.stats.min_elevation,
            route.stats.max_elevation, route.stats.max_gradient,
            route.stats.min_gradient, route.stats.point_count,
        ),
    )
    for idx, p in enumerate(route.points):
        await db.execute(
            """INSERT INTO route_points
               (route_id, idx, lat, lon, elevation_raw, elevation_smoothed,
                cumulative_distance, gradient_raw, gradient_smoothed, bearing)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                route.id, idx, p.lat, p.lon, p.elevation_raw,
                p.elevation_smoothed, p.cumulative_distance,
                p.gradient_raw, p.gradient_smoothed, p.bearing,
            ),
        )
    await db.commit()


def _row_to_stats(row: aiosqlite.Row) -> RouteStats:
    return RouteStats(
        total_distance=row["total_distance"],
        total_ascent=row["total_ascent"],
        total_descent=row["total_descent"],
        min_elevation=row["min_elevation"],
        max_elevation=row["max_elevation"],
        max_gradient=row["max_gradient"],
        min_gradient=row["min_gradient"],
        point_count=row["point_count"],
    )


def _row_to_point(row: aiosqlite.Row) -> RoutePoint:
    return RoutePoint(
        lat=row["lat"],
        lon=row["lon"],
        elevation_raw=row["elevation_raw"],
        elevation_smoothed=row["elevation_smoothed"],
        cumulative_distance=row["cumulative_distance"],
        gradient_raw=row["gradient_raw"],
        gradient_smoothed=row["gradient_smoothed"],
        bearing=row["bearing"],
    )


async def fetch_route(db: aiosqlite.Connection, route_id: str) -> Route:
    cursor = await db.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
    row = await cursor.fetchone()
    if row is None:
        raise RouteNotFoundError(route_id)

    cursor = await db.execute(
        "SELECT * FROM route_points WHERE route_id = ? ORDER BY idx", (route_id,)
    )
    point_rows = await cursor.fetchall()
    points = [_row_to_point(r) for r in point_rows]

    return Route(
        id=row["id"],
        name=row["name"],
        source_filename=row["source_filename"],
        created_at=row["created_at"],
        stats=_row_to_stats(row),
        points=points,
    )


async def fetch_route_metadata(db: aiosqlite.Connection, route_id: str) -> Route:
    cursor = await db.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
    row = await cursor.fetchone()
    if row is None:
        raise RouteNotFoundError(route_id)
    return Route(
        id=row["id"],
        name=row["name"],
        source_filename=row["source_filename"],
        created_at=row["created_at"],
        stats=_row_to_stats(row),
        points=[],
    )


async def list_routes(db: aiosqlite.Connection) -> list[Route]:
    cursor = await db.execute("SELECT * FROM routes ORDER BY created_at DESC")
    rows = await cursor.fetchall()
    return [
        Route(
            id=row["id"],
            name=row["name"],
            source_filename=row["source_filename"],
            created_at=row["created_at"],
            stats=_row_to_stats(row),
            points=[],
        )
        for row in rows
    ]


async def delete_route(db: aiosqlite.Connection, route_id: str) -> None:
    cursor = await db.execute("SELECT id FROM routes WHERE id = ?", (route_id,))
    row = await cursor.fetchone()
    if row is None:
        raise RouteNotFoundError(route_id)
    await db.execute("DELETE FROM routes WHERE id = ?", (route_id,))
    await db.commit()


# --- Ride CRUD ---


async def insert_ride(db: aiosqlite.Connection, ride: Ride) -> None:
    stats_json = None
    if ride.stats is not None:
        stats_json = json.dumps({
            "duration": ride.stats.duration,
            "distance": ride.stats.distance,
            "avg_speed": ride.stats.avg_speed,
            "max_speed": ride.stats.max_speed,
            "avg_power": ride.stats.avg_power,
            "max_power": ride.stats.max_power,
            "avg_cadence": ride.stats.avg_cadence,
            "avg_heart_rate": ride.stats.avg_heart_rate,
            "total_ascent": ride.stats.total_ascent,
        })
    await db.execute(
        """INSERT INTO rides (id, route_id, status, started_at, finished_at, stats_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            ride.id,
            ride.route_id,
            ride.status.value,
            ride.started_at,
            ride.finished_at,
            stats_json,
        ),
    )
    for idx, s in enumerate(ride.samples):
        await db.execute(
            """INSERT INTO ride_samples
               (ride_id, idx, timestamp, distance, speed, power, cadence,
                heart_rate, route_point_idx)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ride.id, idx, s.timestamp, s.distance, s.speed,
                s.power, s.cadence, s.heart_rate, s.route_point_idx,
            ),
        )
    await db.commit()


async def update_ride_status(
    db: aiosqlite.Connection,
    ride_id: str,
    status: RideStatus,
    finished_at: str | None = None,
    stats: RideStats | None = None,
    samples: list[RideSample] | None = None,
) -> None:
    cursor = await db.execute("SELECT id FROM rides WHERE id = ?", (ride_id,))
    if await cursor.fetchone() is None:
        raise RideNotFoundError(ride_id)

    stats_json = None
    if stats is not None:
        stats_json = json.dumps({
            "duration": stats.duration,
            "distance": stats.distance,
            "avg_speed": stats.avg_speed,
            "max_speed": stats.max_speed,
            "avg_power": stats.avg_power,
            "max_power": stats.max_power,
            "avg_cadence": stats.avg_cadence,
            "avg_heart_rate": stats.avg_heart_rate,
            "total_ascent": stats.total_ascent,
        })

    await db.execute(
        """UPDATE rides SET status = ?, finished_at = ?,
           stats_json = COALESCE(?, stats_json) WHERE id = ?""",
        (status.value, finished_at, stats_json, ride_id),
    )

    if samples:
        for idx, s in enumerate(samples):
            await db.execute(
                """INSERT OR REPLACE INTO ride_samples
                   (ride_id, idx, timestamp, distance, speed, power, cadence,
                    heart_rate, route_point_idx)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ride_id, idx, s.timestamp, s.distance, s.speed,
                    s.power, s.cadence, s.heart_rate, s.route_point_idx,
                ),
            )
    await db.commit()


def _row_to_ride_stats(data: dict) -> RideStats:
    return RideStats(
        duration=data["duration"],
        distance=data["distance"],
        avg_speed=data["avg_speed"],
        max_speed=data["max_speed"],
        avg_power=data["avg_power"],
        max_power=data["max_power"],
        avg_cadence=data["avg_cadence"],
        avg_heart_rate=data["avg_heart_rate"],
        total_ascent=data["total_ascent"],
    )


def _row_to_sample(row: aiosqlite.Row) -> RideSample:
    return RideSample(
        timestamp=row["timestamp"],
        distance=row["distance"],
        speed=row["speed"],
        power=row["power"],
        cadence=row["cadence"],
        heart_rate=row["heart_rate"],
        route_point_idx=row["route_point_idx"],
    )


async def fetch_ride(db: aiosqlite.Connection, ride_id: str) -> Ride:
    cursor = await db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,))
    row = await cursor.fetchone()
    if row is None:
        raise RideNotFoundError(ride_id)

    stats = None
    if row["stats_json"]:
        stats = _row_to_ride_stats(json.loads(row["stats_json"]))

    cursor = await db.execute(
        "SELECT * FROM ride_samples WHERE ride_id = ? ORDER BY idx", (ride_id,)
    )
    sample_rows = await cursor.fetchall()
    samples = [_row_to_sample(r) for r in sample_rows]

    return Ride(
        id=row["id"],
        route_id=row["route_id"],
        status=RideStatus(row["status"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        stats=stats,
        samples=samples,
    )


async def fetch_ride_metadata(db: aiosqlite.Connection, ride_id: str) -> Ride:
    cursor = await db.execute("SELECT * FROM rides WHERE id = ?", (ride_id,))
    row = await cursor.fetchone()
    if row is None:
        raise RideNotFoundError(ride_id)

    stats = None
    if row["stats_json"]:
        stats = _row_to_ride_stats(json.loads(row["stats_json"]))

    return Ride(
        id=row["id"],
        route_id=row["route_id"],
        status=RideStatus(row["status"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        stats=stats,
        samples=[],
    )


async def list_rides(db: aiosqlite.Connection) -> list[Ride]:
    cursor = await db.execute("SELECT * FROM rides ORDER BY started_at DESC")
    rows = await cursor.fetchall()
    result = []
    for row in rows:
        stats = None
        if row["stats_json"]:
            stats = _row_to_ride_stats(json.loads(row["stats_json"]))
        result.append(Ride(
            id=row["id"],
            route_id=row["route_id"],
            status=RideStatus(row["status"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            stats=stats,
            samples=[],
        ))
    return result


async def delete_ride(db: aiosqlite.Connection, ride_id: str) -> None:
    cursor = await db.execute("SELECT id FROM rides WHERE id = ?", (ride_id,))
    if await cursor.fetchone() is None:
        raise RideNotFoundError(ride_id)
    await db.execute("DELETE FROM rides WHERE id = ?", (ride_id,))
    await db.commit()


# --- Trainer Profile CRUD ---


def _row_to_profile(row: aiosqlite.Row) -> TrainerProfile:
    return TrainerProfile(
        id=row["id"],
        name=row["name"],
        trainer_type=TrainerType(row["trainer_type"]),
        trainer_address=row["trainer_address"],
        speed_sensor_address=row["speed_sensor_address"],
        cadence_sensor_address=row["cadence_sensor_address"],
        power_meter_address=row["power_meter_address"],
        hrm_address=row["hrm_address"],
        resistance_factor=row["resistance_factor"],
        wheel_circumference=row["wheel_circumference"],
        is_default=bool(row["is_default"]),
    )


async def insert_profile(db: aiosqlite.Connection, profile: TrainerProfile) -> None:
    await db.execute(
        """INSERT INTO trainer_profiles
           (id, name, trainer_type, trainer_address, speed_sensor_address,
            cadence_sensor_address, power_meter_address, hrm_address,
            resistance_factor, wheel_circumference, is_default)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            profile.id, profile.name, profile.trainer_type.value,
            profile.trainer_address, profile.speed_sensor_address,
            profile.cadence_sensor_address, profile.power_meter_address,
            profile.hrm_address, profile.resistance_factor,
            profile.wheel_circumference, int(profile.is_default),
        ),
    )
    await db.commit()


async def fetch_profile(db: aiosqlite.Connection, profile_id: str) -> TrainerProfile:
    cursor = await db.execute(
        "SELECT * FROM trainer_profiles WHERE id = ?", (profile_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        raise ProfileNotFoundError(profile_id)
    return _row_to_profile(row)


async def list_profiles(db: aiosqlite.Connection) -> list[TrainerProfile]:
    cursor = await db.execute("SELECT * FROM trainer_profiles ORDER BY name")
    rows = await cursor.fetchall()
    return [_row_to_profile(r) for r in rows]


async def update_profile(
    db: aiosqlite.Connection, profile: TrainerProfile
) -> None:
    cursor = await db.execute(
        "SELECT id FROM trainer_profiles WHERE id = ?", (profile.id,)
    )
    if await cursor.fetchone() is None:
        raise ProfileNotFoundError(profile.id)
    await db.execute(
        """UPDATE trainer_profiles SET
           name = ?, trainer_type = ?, trainer_address = ?,
           speed_sensor_address = ?, cadence_sensor_address = ?,
           power_meter_address = ?, hrm_address = ?,
           resistance_factor = ?, wheel_circumference = ?, is_default = ?
           WHERE id = ?""",
        (
            profile.name, profile.trainer_type.value, profile.trainer_address,
            profile.speed_sensor_address, profile.cadence_sensor_address,
            profile.power_meter_address, profile.hrm_address,
            profile.resistance_factor, profile.wheel_circumference,
            int(profile.is_default), profile.id,
        ),
    )
    await db.commit()


async def delete_profile(db: aiosqlite.Connection, profile_id: str) -> None:
    cursor = await db.execute(
        "SELECT id FROM trainer_profiles WHERE id = ?", (profile_id,)
    )
    if await cursor.fetchone() is None:
        raise ProfileNotFoundError(profile_id)
    await db.execute("DELETE FROM trainer_profiles WHERE id = ?", (profile_id,))
    await db.commit()


async def get_default_profile(
    db: aiosqlite.Connection,
) -> TrainerProfile | None:
    cursor = await db.execute(
        "SELECT * FROM trainer_profiles WHERE is_default = 1 LIMIT 1"
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_profile(row)


async def set_default_profile(
    db: aiosqlite.Connection, profile_id: str
) -> None:
    cursor = await db.execute(
        "SELECT id FROM trainer_profiles WHERE id = ?", (profile_id,)
    )
    if await cursor.fetchone() is None:
        raise ProfileNotFoundError(profile_id)
    # Clear all defaults, then set the new one
    await db.execute("UPDATE trainer_profiles SET is_default = 0")
    await db.execute(
        "UPDATE trainer_profiles SET is_default = 1 WHERE id = ?", (profile_id,)
    )
    await db.commit()


# --- Settings CRUD ---


async def get_settings(db: aiosqlite.Connection) -> UserSettings:
    cursor = await db.execute("SELECT key, value FROM user_settings")
    rows = await cursor.fetchall()
    data = {row["key"]: row["value"] for row in rows}
    return UserSettings(
        ftp=int(data.get("ftp", "200")),
        weight=float(data.get("weight", "75.0")),
        trainer_device_id=data.get("trainer_device_id"),
        hrm_device_id=data.get("hrm_device_id"),
        strava_access_token=data.get("strava_access_token"),
        strava_refresh_token=data.get("strava_refresh_token"),
        elevation_smoothing_window=int(data.get("elevation_smoothing_window", "5")),
    )


async def save_settings(db: aiosqlite.Connection, settings: UserSettings) -> None:
    pairs = {
        "ftp": str(settings.ftp),
        "weight": str(settings.weight),
        "elevation_smoothing_window": str(settings.elevation_smoothing_window),
    }
    if settings.trainer_device_id is not None:
        pairs["trainer_device_id"] = settings.trainer_device_id
    if settings.hrm_device_id is not None:
        pairs["hrm_device_id"] = settings.hrm_device_id
    if settings.strava_access_token is not None:
        pairs["strava_access_token"] = settings.strava_access_token
    if settings.strava_refresh_token is not None:
        pairs["strava_refresh_token"] = settings.strava_refresh_token

    for key, value in pairs.items():
        await db.execute(
            "INSERT OR REPLACE INTO user_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    await db.commit()
