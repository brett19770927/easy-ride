from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from easy_ride.api.app import create_app
from easy_ride.config import Config


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
async def client(tmp_path):
    config = Config(data_dir=tmp_path)
    app = create_app(config)
    config.ensure_dirs()
    from easy_ride.db import connect_db, init_db
    db = await connect_db(config.db_path)
    await init_db(db)
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    # Clean up active engines
    from easy_ride.api.ride_routes import _active_engines
    for engine in list(_active_engines.values()):
        try:
            await engine.stop()
        except Exception:
            pass
    _active_engines.clear()
    await db.close()


async def _upload_route(client) -> str:
    gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
    resp = await client.post(
        "/api/routes",
        files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
    )
    return resp.json()["id"]


class TestSettingsAPI:
    async def test_get_defaults(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ftp"] == 200
        assert data["weight"] == 75.0

    async def test_update_settings(self, client):
        resp = await client.put(
            "/api/settings",
            json={"ftp": 280, "weight": 82.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ftp"] == 280
        assert data["weight"] == 82.5

    async def test_partial_update(self, client):
        await client.put("/api/settings", json={"ftp": 300})
        resp = await client.get("/api/settings")
        data = resp.json()
        assert data["ftp"] == 300
        assert data["weight"] == 75.0  # Unchanged


class TestDeviceAPI:
    async def test_scan_endpoint_exists(self, client):
        # Scan may fail without BLE hardware, but endpoint should exist
        resp = await client.get("/api/devices/scan")
        assert resp.status_code in (200, 500, 501)


class TestRideAPI:
    async def test_start_ride_with_simulator(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "active"
        assert data["route_id"] == route_id
        # Clean up
        await client.patch(f"/api/rides/{data['id']}/stop")

    async def test_start_ride_bad_route(self, client):
        resp = await client.post(
            "/api/rides",
            json={"route_id": "nonexistent", "use_simulator": True},
        )
        assert resp.status_code == 404

    async def test_list_rides(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        ride_id = resp.json()["id"]
        resp = await client.get("/api/rides")
        assert resp.status_code == 200
        assert len(resp.json()["rides"]) >= 1
        await client.patch(f"/api/rides/{ride_id}/stop")

    async def test_get_ride_detail(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        ride_id = resp.json()["id"]
        await asyncio.sleep(1.5)
        resp = await client.get(f"/api/rides/{ride_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == ride_id
        assert len(data["samples"]) >= 1
        await client.patch(f"/api/rides/{ride_id}/stop")

    async def test_pause_resume(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        ride_id = resp.json()["id"]
        await asyncio.sleep(0.5)

        resp = await client.patch(f"/api/rides/{ride_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        resp = await client.patch(f"/api/rides/{ride_id}/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

        await client.patch(f"/api/rides/{ride_id}/stop")

    async def test_stop_ride(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        ride_id = resp.json()["id"]
        await asyncio.sleep(1.5)

        resp = await client.patch(f"/api/rides/{ride_id}/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["finished_at"] is not None

    async def test_stop_persists_stats(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        ride_id = resp.json()["id"]
        await asyncio.sleep(2.5)

        await client.patch(f"/api/rides/{ride_id}/stop")
        # Fetch from DB (engine removed from active)
        resp = await client.get(f"/api/rides/{ride_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"] is not None
        assert data["stats"]["avg_power"] > 0

    async def test_delete_ride(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        ride_id = resp.json()["id"]
        await client.patch(f"/api/rides/{ride_id}/stop")
        resp = await client.delete(f"/api/rides/{ride_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/rides/{ride_id}")
        assert resp.status_code == 404

    async def test_get_nonexistent_ride_404(self, client):
        resp = await client.get("/api/rides/nonexistent")
        assert resp.status_code == 404

    async def test_delete_nonexistent_ride_404(self, client):
        resp = await client.delete("/api/rides/nonexistent")
        assert resp.status_code == 404

    async def test_pause_nonexistent_404(self, client):
        resp = await client.patch("/api/rides/nonexistent/pause")
        assert resp.status_code == 404
