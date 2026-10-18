from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from easy_ride.api.app import create_app
from easy_ride.config import Config


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
    await db.close()


class TestProfileAPI:
    async def test_create_profile(self, client):
        resp = await client.post("/api/profiles", json={
            "name": "My Smart Trainer",
            "trainer_type": "smart",
            "trainer_address": "AA:BB:CC:DD:EE:FF",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Smart Trainer"
        assert data["trainer_type"] == "smart"
        assert data["id"]  # Should have an ID

    async def test_list_profiles(self, client):
        await client.post("/api/profiles", json={
            "name": "Trainer A", "trainer_type": "smart",
        })
        await client.post("/api/profiles", json={
            "name": "Trainer B", "trainer_type": "classic",
        })
        resp = await client.get("/api/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["profiles"]) == 2

    async def test_get_profile(self, client):
        resp = await client.post("/api/profiles", json={
            "name": "Test", "trainer_type": "smart",
        })
        profile_id = resp.json()["id"]
        resp = await client.get(f"/api/profiles/{profile_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test"

    async def test_get_nonexistent_404(self, client):
        resp = await client.get("/api/profiles/nonexistent")
        assert resp.status_code == 404

    async def test_update_profile(self, client):
        resp = await client.post("/api/profiles", json={
            "name": "Old Name", "trainer_type": "smart",
        })
        profile_id = resp.json()["id"]
        resp = await client.put(f"/api/profiles/{profile_id}", json={
            "name": "New Name", "trainer_type": "classic",
            "resistance_factor": 25.0,
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["trainer_type"] == "classic"
        assert resp.json()["resistance_factor"] == 25.0

    async def test_update_nonexistent_404(self, client):
        resp = await client.put("/api/profiles/nonexistent", json={
            "name": "X", "trainer_type": "smart",
        })
        assert resp.status_code == 404

    async def test_delete_profile(self, client):
        resp = await client.post("/api/profiles", json={
            "name": "Delete Me", "trainer_type": "smart",
        })
        profile_id = resp.json()["id"]
        resp = await client.delete(f"/api/profiles/{profile_id}")
        assert resp.status_code == 204
        resp = await client.get(f"/api/profiles/{profile_id}")
        assert resp.status_code == 404

    async def test_delete_nonexistent_404(self, client):
        resp = await client.delete("/api/profiles/nonexistent")
        assert resp.status_code == 404

    async def test_invalid_trainer_type(self, client):
        resp = await client.post("/api/profiles", json={
            "name": "Bad", "trainer_type": "invalid",
        })
        assert resp.status_code == 400

    async def test_create_default_profile(self, client):
        resp = await client.post("/api/profiles", json={
            "name": "Default", "trainer_type": "smart", "is_default": True,
        })
        assert resp.status_code == 201
        assert resp.json()["is_default"] is True

    async def test_classic_profile_fields(self, client):
        resp = await client.post("/api/profiles", json={
            "name": "Classic Setup",
            "trainer_type": "classic",
            "speed_sensor_address": "11:22:33:44:55:66",
            "power_meter_address": "AA:BB:CC:DD:EE:FF",
            "resistance_factor": 22.5,
            "wheel_circumference": 2.08,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["trainer_type"] == "classic"
        assert data["speed_sensor_address"] == "11:22:33:44:55:66"
        assert data["resistance_factor"] == 22.5
