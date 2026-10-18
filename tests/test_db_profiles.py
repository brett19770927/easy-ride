from __future__ import annotations

import uuid

import pytest

from easy_ride.db import (
    connect_db,
    delete_profile,
    fetch_profile,
    get_default_profile,
    init_db,
    insert_profile,
    list_profiles,
    set_default_profile,
    update_profile,
)
from easy_ride.exceptions import ProfileNotFoundError
from easy_ride.models import TrainerProfile, TrainerType


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await connect_db(db_path)
    await init_db(conn)
    yield conn
    await conn.close()


def _make_profile(**kwargs) -> TrainerProfile:
    defaults = dict(
        id=str(uuid.uuid4()),
        name="Test Profile",
        trainer_type=TrainerType.SMART,
        trainer_address="AA:BB:CC:DD:EE:FF",
    )
    defaults.update(kwargs)
    return TrainerProfile(**defaults)


class TestProfileCRUD:
    async def test_insert_and_fetch(self, db):
        profile = _make_profile(name="My Trainer")
        await insert_profile(db, profile)
        fetched = await fetch_profile(db, profile.id)
        assert fetched.name == "My Trainer"
        assert fetched.trainer_type == TrainerType.SMART

    async def test_list_profiles(self, db):
        p1 = _make_profile(name="Alpha")
        p2 = _make_profile(name="Beta")
        await insert_profile(db, p1)
        await insert_profile(db, p2)
        profiles = await list_profiles(db)
        assert len(profiles) == 2
        # Ordered by name
        assert profiles[0].name == "Alpha"
        assert profiles[1].name == "Beta"

    async def test_update_profile(self, db):
        profile = _make_profile(name="Old Name")
        await insert_profile(db, profile)
        profile.name = "New Name"
        profile.trainer_type = TrainerType.CLASSIC
        await update_profile(db, profile)
        fetched = await fetch_profile(db, profile.id)
        assert fetched.name == "New Name"
        assert fetched.trainer_type == TrainerType.CLASSIC

    async def test_delete_profile(self, db):
        profile = _make_profile()
        await insert_profile(db, profile)
        await delete_profile(db, profile.id)
        with pytest.raises(ProfileNotFoundError):
            await fetch_profile(db, profile.id)

    async def test_fetch_nonexistent_raises(self, db):
        with pytest.raises(ProfileNotFoundError):
            await fetch_profile(db, "nonexistent")

    async def test_delete_nonexistent_raises(self, db):
        with pytest.raises(ProfileNotFoundError):
            await delete_profile(db, "nonexistent")

    async def test_update_nonexistent_raises(self, db):
        profile = _make_profile()
        with pytest.raises(ProfileNotFoundError):
            await update_profile(db, profile)


class TestDefaultProfile:
    async def test_no_default_returns_none(self, db):
        result = await get_default_profile(db)
        assert result is None

    async def test_set_default(self, db):
        profile = _make_profile()
        await insert_profile(db, profile)
        await set_default_profile(db, profile.id)
        default = await get_default_profile(db)
        assert default is not None
        assert default.id == profile.id
        assert default.is_default is True

    async def test_set_default_clears_previous(self, db):
        p1 = _make_profile(name="First", is_default=True)
        p2 = _make_profile(name="Second")
        await insert_profile(db, p1)
        await insert_profile(db, p2)
        await set_default_profile(db, p2.id)
        default = await get_default_profile(db)
        assert default.id == p2.id
        # First should no longer be default
        p1_fetched = await fetch_profile(db, p1.id)
        assert p1_fetched.is_default is False

    async def test_set_default_nonexistent_raises(self, db):
        with pytest.raises(ProfileNotFoundError):
            await set_default_profile(db, "nonexistent")

    async def test_profile_with_all_fields(self, db):
        profile = _make_profile(
            trainer_type=TrainerType.CLASSIC,
            speed_sensor_address="11:22:33:44:55:66",
            power_meter_address="AA:BB:CC:DD:EE:FF",
            hrm_address="FF:EE:DD:CC:BB:AA",
            resistance_factor=25.0,
            wheel_circumference=2.08,
        )
        await insert_profile(db, profile)
        fetched = await fetch_profile(db, profile.id)
        assert fetched.speed_sensor_address == "11:22:33:44:55:66"
        assert fetched.resistance_factor == 25.0
        assert fetched.wheel_circumference == 2.08
