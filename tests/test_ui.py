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
    config.ensure_dirs()
    from easy_ride.db import connect_db, init_db
    db = await connect_db(config.db_path)
    await init_db(db)
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close()


async def _upload_route(client: AsyncClient) -> str:
    """Helper: upload a GPX file and return the route ID."""
    gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
    resp = await client.post(
        "/api/routes",
        files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
    )
    return resp.json()["id"]


class TestDashboard:
    async def test_dashboard_returns_200(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_dashboard_has_heading(self, client):
        resp = await client.get("/")
        assert "<h1>Dashboard</h1>" in resp.text

    async def test_dashboard_has_skip_link(self, client):
        resp = await client.get("/")
        assert 'class="skip-link"' in resp.text
        assert 'href="#main-content"' in resp.text

    async def test_dashboard_has_nav(self, client):
        resp = await client.get("/")
        assert 'aria-label="Main navigation"' in resp.text


class TestRoutesPage:
    async def test_routes_page_returns_200(self, client):
        resp = await client.get("/routes")
        assert resp.status_code == 200
        assert "Routes" in resp.text

    async def test_routes_page_has_upload_form(self, client):
        resp = await client.get("/routes")
        assert 'enctype="multipart/form-data"' in resp.text
        assert 'name="file"' in resp.text


class TestRouteDetail:
    async def test_route_detail_returns_200(self, client):
        route_id = await _upload_route(client)
        resp = await client.get(f"/routes/{route_id}")
        assert resp.status_code == 200
        assert "Simple Loop" in resp.text

    async def test_route_detail_has_start_ride_link(self, client):
        route_id = await _upload_route(client)
        resp = await client.get(f"/routes/{route_id}")
        assert "Start Ride" in resp.text

    async def test_route_detail_404_nonexistent(self, client):
        resp = await client.get("/routes/nonexistent")
        assert resp.status_code == 404


class TestUploadRoute:
    async def test_upload_redirects_to_detail(self, client):
        gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
        resp = await client.post(
            "/routes/upload",
            files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/routes/")


class TestRidesPage:
    async def test_rides_page_returns_200(self, client):
        resp = await client.get("/rides")
        assert resp.status_code == 200
        assert "Ride History" in resp.text


class TestRideStartPage:
    async def test_ride_start_page_returns_200(self, client):
        route_id = await _upload_route(client)
        resp = await client.get(f"/ride/start?route_id={route_id}")
        assert resp.status_code == 200
        assert "Start Ride" in resp.text
        assert "Simulator" in resp.text


class TestSettingsPage:
    async def test_settings_returns_200(self, client):
        resp = await client.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text

    async def test_settings_has_form_fields(self, client):
        resp = await client.get("/settings")
        assert 'name="ftp"' in resp.text
        assert 'name="weight"' in resp.text

    async def test_save_settings_redirects(self, client):
        resp = await client.post(
            "/settings",
            data={"ftp": "250", "weight": "80.0", "elevation_smoothing_window": "5"},
            follow_redirects=False,
        )
        assert resp.status_code == 303

    async def test_saved_settings_persist(self, client):
        await client.post(
            "/settings",
            data={"ftp": "250", "weight": "80.0", "elevation_smoothing_window": "7"},
        )
        resp = await client.get("/settings")
        assert 'value="250"' in resp.text
        assert 'value="80.0"' in resp.text


class TestProfilesPage:
    async def test_profiles_returns_200(self, client):
        resp = await client.get("/profiles")
        assert resp.status_code == 200
        assert "Trainer Profiles" in resp.text

    async def test_new_profile_form_returns_200(self, client):
        resp = await client.get("/profiles/new")
        assert resp.status_code == 200
        assert "Create Profile" in resp.text


class TestDevicesPage:
    async def test_devices_returns_200(self, client):
        resp = await client.get("/devices")
        assert resp.status_code == 200
        assert "BLE Devices" in resp.text

    async def test_devices_has_scan_button(self, client):
        resp = await client.get("/devices")
        assert "Scan for Devices" in resp.text


class TestBaseTemplateOnAllPages:
    """Verify accessibility elements are present on every page."""

    @pytest.mark.parametrize("path", [
        "/", "/routes", "/rides", "/settings", "/profiles", "/profiles/new", "/devices",
    ])
    async def test_skip_link_on_every_page(self, client, path):
        resp = await client.get(path)
        assert resp.status_code == 200
        assert "skip-link" in resp.text

    @pytest.mark.parametrize("path", [
        "/", "/routes", "/rides", "/settings", "/profiles", "/devices",
    ])
    async def test_nav_on_every_page(self, client, path):
        resp = await client.get(path)
        assert 'aria-label="Main navigation"' in resp.text

    @pytest.mark.parametrize("path", [
        "/", "/routes", "/rides", "/settings", "/profiles", "/devices",
    ])
    async def test_main_landmark_on_every_page(self, client, path):
        resp = await client.get(path)
        assert 'id="main-content"' in resp.text
