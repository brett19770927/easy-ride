from __future__ import annotations

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
    # Manually run lifespan since ASGITransport doesn't trigger it
    config.ensure_dirs()
    from easy_ride.db import connect_db, init_db
    db = await connect_db(config.db_path)
    await init_db(db)
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close()


class TestRouteAPI:
    async def test_upload_gpx(self, client):
        gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
        response = await client.post(
            "/api/routes",
            files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Simple Loop"
        assert "id" in data
        assert data["stats"]["point_count"] == 5

    async def test_list_routes_empty(self, client):
        response = await client.get("/api/routes")
        assert response.status_code == 200
        assert response.json()["routes"] == []

    async def test_list_routes_after_upload(self, client):
        gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
        await client.post(
            "/api/routes",
            files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
        )
        response = await client.get("/api/routes")
        assert len(response.json()["routes"]) == 1

    async def test_get_route_detail(self, client):
        gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
        upload = await client.post(
            "/api/routes",
            files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
        )
        route_id = upload.json()["id"]
        response = await client.get(f"/api/routes/{route_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["points"]) == 5
        assert data["points"][0]["lat"] == pytest.approx(51.5074)

    async def test_delete_route(self, client):
        gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
        upload = await client.post(
            "/api/routes",
            files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
        )
        route_id = upload.json()["id"]
        response = await client.delete(f"/api/routes/{route_id}")
        assert response.status_code == 204

        response = await client.get(f"/api/routes/{route_id}")
        assert response.status_code == 404

    async def test_get_nonexistent_404(self, client):
        response = await client.get("/api/routes/nonexistent")
        assert response.status_code == 404

    async def test_delete_nonexistent_404(self, client):
        response = await client.delete("/api/routes/nonexistent")
        assert response.status_code == 404

    async def test_upload_invalid_gpx(self, client):
        response = await client.post(
            "/api/routes",
            files={"file": ("bad.gpx", b"<not valid xml", "application/gpx+xml")},
        )
        assert response.status_code == 400

    async def test_upload_mountain_climb(self, client):
        gpx_data = (FIXTURES_DIR / "mountain_climb.gpx").read_bytes()
        response = await client.post(
            "/api/routes",
            files={"file": ("mountain_climb.gpx", gpx_data, "application/gpx+xml")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Mountain Climb"
        assert data["stats"]["total_ascent"] > 0

    async def test_upload_with_custom_name(self, client):
        gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
        response = await client.post(
            "/api/routes",
            files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
            data={"name": "My Sunday Ride"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "My Sunday Ride"

    async def test_upload_without_name_uses_gpx_metadata(self, client):
        gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
        response = await client.post(
            "/api/routes",
            files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "Simple Loop"
