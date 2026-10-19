from __future__ import annotations

import pytest

from easy_ride.db import (
    clear_strava_tokens,
    connect_db,
    delete_ride,
    fetch_ride,
    fetch_ride_metadata,
    get_settings,
    init_db,
    insert_ride,
    insert_route,
    list_rides,
    save_settings,
    set_ride_strava_activity,
    update_ride_status,
)
from easy_ride.exceptions import RideNotFoundError
from easy_ride.models import (
    Ride,
    RideSample,
    RideStats,
    RideStatus,
    UserSettings,
)


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await connect_db(db_path)
    await init_db(conn)
    yield conn
    await conn.close()


def _make_ride(route_id: str = "route-1") -> Ride:
    return Ride(
        id="ride-1",
        route_id=route_id,
        status=RideStatus.ACTIVE,
        started_at="2024-01-01T10:00:00Z",
        samples=[
            RideSample(
                timestamp=1704103200.0,
                distance=10.0,
                speed=5.0,
                power=150,
                cadence=85,
                heart_rate=130,
                route_point_idx=0,
            ),
            RideSample(
                timestamp=1704103201.0,
                distance=15.0,
                speed=5.5,
                power=160,
                cadence=87,
                heart_rate=132,
                route_point_idx=1,
            ),
        ],
    )


class TestRideCRUD:
    async def test_insert_and_fetch(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        fetched = await fetch_ride(db, "ride-1")
        assert fetched.id == "ride-1"
        assert fetched.route_id == sample_route.id
        assert fetched.status == RideStatus.ACTIVE
        assert len(fetched.samples) == 2

    async def test_fetch_metadata_no_samples(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        fetched = await fetch_ride_metadata(db, "ride-1")
        assert fetched.id == "ride-1"
        assert fetched.samples == []

    async def test_list_rides(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        rides = await list_rides(db)
        assert len(rides) == 1
        assert rides[0].id == "ride-1"

    async def test_delete_ride(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        await delete_ride(db, "ride-1")
        rides = await list_rides(db)
        assert len(rides) == 0

    async def test_delete_cascades_samples(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        await delete_ride(db, "ride-1")
        cursor = await db.execute(
            "SELECT COUNT(*) FROM ride_samples WHERE ride_id = ?", ("ride-1",)
        )
        row = await cursor.fetchone()
        assert row[0] == 0

    async def test_fetch_nonexistent_raises(self, db):
        with pytest.raises(RideNotFoundError):
            await fetch_ride(db, "nonexistent")

    async def test_delete_nonexistent_raises(self, db):
        with pytest.raises(RideNotFoundError):
            await delete_ride(db, "nonexistent")

    async def test_update_status_with_stats(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        stats = RideStats(
            duration=120.0, distance=500.0, avg_speed=4.2, max_speed=8.0,
            avg_power=165, max_power=300, avg_cadence=82, avg_heart_rate=140,
            total_ascent=25.0,
        )
        await update_ride_status(
            db, "ride-1", RideStatus.COMPLETED,
            finished_at="2024-01-01T10:02:00Z", stats=stats,
        )
        fetched = await fetch_ride(db, "ride-1")
        assert fetched.status == RideStatus.COMPLETED
        assert fetched.finished_at == "2024-01-01T10:02:00Z"
        assert fetched.stats is not None
        assert fetched.stats.avg_power == 165
        assert fetched.stats.total_ascent == pytest.approx(25.0)

    async def test_sample_roundtrip(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        fetched = await fetch_ride(db, "ride-1")
        s = fetched.samples[0]
        assert s.distance == pytest.approx(10.0)
        assert s.speed == pytest.approx(5.0)
        assert s.power == 150
        assert s.cadence == 85
        assert s.heart_rate == 130
        assert s.route_point_idx == 0


class TestSettingsCRUD:
    async def test_defaults(self, db):
        settings = await get_settings(db)
        assert settings.ftp == 200
        assert settings.weight == 75.0
        assert settings.trainer_device_id is None
        assert settings.elevation_smoothing_window == 5

    async def test_save_and_load(self, db):
        settings = UserSettings(ftp=250, weight=80.0, elevation_smoothing_window=7)
        await save_settings(db, settings)
        loaded = await get_settings(db)
        assert loaded.ftp == 250
        assert loaded.weight == 80.0
        assert loaded.elevation_smoothing_window == 7

    async def test_update_partial(self, db):
        settings = UserSettings(ftp=250, weight=80.0)
        await save_settings(db, settings)
        # Update just FTP
        settings2 = UserSettings(ftp=300, weight=80.0)
        await save_settings(db, settings2)
        loaded = await get_settings(db)
        assert loaded.ftp == 300
        assert loaded.weight == 80.0

    async def test_device_ids(self, db):
        settings = UserSettings(
            trainer_device_id="AA:BB:CC:DD:EE:FF",
            hrm_device_id="11:22:33:44:55:66",
        )
        await save_settings(db, settings)
        loaded = await get_settings(db)
        assert loaded.trainer_device_id == "AA:BB:CC:DD:EE:FF"
        assert loaded.hrm_device_id == "11:22:33:44:55:66"


class TestStravaActivityId:
    async def test_ride_strava_activity_id_default_none(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        fetched = await fetch_ride(db, "ride-1")
        assert fetched.strava_activity_id is None

    async def test_set_and_fetch_strava_activity_id(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        await set_ride_strava_activity(db, "ride-1", 12345678)
        fetched = await fetch_ride(db, "ride-1")
        assert fetched.strava_activity_id == 12345678

    async def test_strava_activity_id_in_metadata(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        await set_ride_strava_activity(db, "ride-1", 99999)
        fetched = await fetch_ride_metadata(db, "ride-1")
        assert fetched.strava_activity_id == 99999

    async def test_strava_activity_id_in_list(self, db, sample_route):
        await insert_route(db, sample_route)
        ride = _make_ride(sample_route.id)
        await insert_ride(db, ride)
        await set_ride_strava_activity(db, "ride-1", 55555)
        rides = await list_rides(db)
        assert rides[0].strava_activity_id == 55555

    async def test_set_strava_activity_nonexistent_ride(self, db):
        with pytest.raises(RideNotFoundError):
            await set_ride_strava_activity(db, "nonexistent", 12345)


class TestStravaTokens:
    async def test_strava_tokens_roundtrip(self, db):
        settings = UserSettings(
            strava_access_token="access_abc",
            strava_refresh_token="refresh_xyz",
            strava_expires_at=1700000000,
        )
        await save_settings(db, settings)
        loaded = await get_settings(db)
        assert loaded.strava_access_token == "access_abc"
        assert loaded.strava_refresh_token == "refresh_xyz"
        assert loaded.strava_expires_at == 1700000000

    async def test_clear_strava_tokens(self, db):
        settings = UserSettings(
            strava_access_token="access_abc",
            strava_refresh_token="refresh_xyz",
            strava_expires_at=1700000000,
        )
        await save_settings(db, settings)
        await clear_strava_tokens(db)
        loaded = await get_settings(db)
        assert loaded.strava_access_token is None
        assert loaded.strava_refresh_token is None
        assert loaded.strava_expires_at is None
