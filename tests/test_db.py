from __future__ import annotations

import pytest

import aiosqlite

from easy_ride.db import (
    connect_db,
    delete_route,
    fetch_route,
    fetch_route_metadata,
    init_db,
    insert_route,
    list_routes,
)
from easy_ride.exceptions import RouteNotFoundError
from easy_ride.gpx.processor import process_gpx


@pytest.fixture
async def db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = await connect_db(db_path)
    await init_db(conn)
    yield conn
    await conn.close()


@pytest.fixture
def sample_route(simple_loop_gpx):
    return process_gpx(simple_loop_gpx, filename="simple_loop.gpx")


class TestDatabase:
    async def test_init_creates_tables(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "routes" in tables
        assert "route_points" in tables
        assert "schema_version" in tables

    async def test_insert_and_fetch(self, db, sample_route):
        await insert_route(db, sample_route)
        fetched = await fetch_route(db, sample_route.id)
        assert fetched.id == sample_route.id
        assert fetched.name == sample_route.name
        assert len(fetched.points) == len(sample_route.points)

    async def test_fetch_metadata_no_points(self, db, sample_route):
        await insert_route(db, sample_route)
        fetched = await fetch_route_metadata(db, sample_route.id)
        assert fetched.id == sample_route.id
        assert fetched.points == []

    async def test_list_routes(self, db, sample_route):
        await insert_route(db, sample_route)
        routes = await list_routes(db)
        assert len(routes) == 1
        assert routes[0].id == sample_route.id

    async def test_delete_route(self, db, sample_route):
        await insert_route(db, sample_route)
        await delete_route(db, sample_route.id)
        routes = await list_routes(db)
        assert len(routes) == 0

    async def test_delete_cascades_points(self, db, sample_route):
        await insert_route(db, sample_route)
        await delete_route(db, sample_route.id)
        cursor = await db.execute(
            "SELECT COUNT(*) FROM route_points WHERE route_id = ?",
            (sample_route.id,),
        )
        row = await cursor.fetchone()
        assert row[0] == 0

    async def test_fetch_nonexistent_raises(self, db):
        with pytest.raises(RouteNotFoundError):
            await fetch_route(db, "nonexistent")

    async def test_delete_nonexistent_raises(self, db):
        with pytest.raises(RouteNotFoundError):
            await delete_route(db, "nonexistent")

    async def test_stats_roundtrip(self, db, sample_route):
        await insert_route(db, sample_route)
        fetched = await fetch_route(db, sample_route.id)
        assert fetched.stats.total_distance == pytest.approx(
            sample_route.stats.total_distance
        )
        assert fetched.stats.point_count == sample_route.stats.point_count
