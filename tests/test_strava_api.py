from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from easy_ride.api.app import create_app
from easy_ride.config import Config
from easy_ride.db import connect_db, get_settings, init_db, save_settings
from easy_ride.models import UserSettings


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
async def client(tmp_path):
    config = Config(
        data_dir=tmp_path,
        strava_client_id="test_client_id",
        strava_client_secret="test_client_secret",
    )
    app = create_app(config)
    config.ensure_dirs()
    db = await connect_db(config.db_path)
    await init_db(db)
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    from easy_ride.api.ride_routes import _active_engines
    for engine in list(_active_engines.values()):
        try:
            await engine.stop()
        except Exception:
            pass
    _active_engines.clear()
    await db.close()


@pytest.fixture
async def unconfigured_client(tmp_path):
    """Client without Strava credentials configured."""
    config = Config(data_dir=tmp_path)
    app = create_app(config)
    config.ensure_dirs()
    db = await connect_db(config.db_path)
    await init_db(db)
    app.state.db = db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close()


async def _upload_route(client) -> str:
    gpx_data = (FIXTURES_DIR / "simple_loop.gpx").read_bytes()
    resp = await client.post(
        "/api/routes",
        files={"file": ("simple_loop.gpx", gpx_data, "application/gpx+xml")},
    )
    return resp.json()["id"]


async def _create_completed_ride(client) -> str:
    route_id = await _upload_route(client)
    resp = await client.post(
        "/api/rides",
        json={"route_id": route_id, "use_simulator": True},
    )
    ride_id = resp.json()["id"]
    await asyncio.sleep(1.5)
    await client.patch(f"/api/rides/{ride_id}/stop")
    return ride_id


class TestStravaConnect:
    async def test_connect_returns_url(self, client):
        resp = await client.get("/api/strava/connect")
        assert resp.status_code == 200
        data = resp.json()
        assert "authorize_url" in data
        assert "client_id=test_client_id" in data["authorize_url"]
        assert "activity:write" in data["authorize_url"]

    async def test_connect_not_configured(self, unconfigured_client):
        resp = await unconfigured_client.get("/api/strava/connect")
        assert resp.status_code == 400


class TestStravaCallback:
    async def test_successful_callback(self, client):
        mock_tokens = {
            "access_token": "access_abc",
            "refresh_token": "refresh_xyz",
            "expires_at": 1700000000,
        }
        with patch(
            "easy_ride.api.strava_routes.exchange_token",
            new_callable=AsyncMock,
            return_value=mock_tokens,
        ):
            resp = await client.get("/api/strava/callback?code=test_code")
        assert resp.status_code == 200
        assert resp.json()["status"] == "connected"

        # Verify tokens stored in settings
        db = client._transport.app.state.db
        settings = await get_settings(db)
        assert settings.strava_access_token == "access_abc"
        assert settings.strava_refresh_token == "refresh_xyz"
        assert settings.strava_expires_at == 1700000000

    async def test_callback_bad_code(self, client):
        with patch(
            "easy_ride.api.strava_routes.exchange_token",
            new_callable=AsyncMock,
            side_effect=__import__("easy_ride.exceptions", fromlist=["StravaAuthError"]).StravaAuthError("bad code"),
        ):
            resp = await client.get("/api/strava/callback?code=bad")
        assert resp.status_code == 401


class TestStravaStatus:
    async def test_not_connected(self, client):
        resp = await client.get("/api/strava/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False

    async def test_connected(self, client):
        # Store tokens first
        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_refresh_token = "refresh_xyz"
        settings.strava_expires_at = 9999999999
        await save_settings(db, settings)

        resp = await client.get("/api/strava/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["expired"] is False


class TestStravaDisconnect:
    async def test_disconnect(self, client):
        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_refresh_token = "refresh_xyz"
        settings.strava_expires_at = 1700000000
        await save_settings(db, settings)

        resp = await client.post("/api/strava/disconnect")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disconnected"

        settings = await get_settings(db)
        assert settings.strava_access_token is None
        assert settings.strava_refresh_token is None


class TestStravaUpload:
    async def test_upload_ride(self, client):
        ride_id = await _create_completed_ride(client)

        # Store tokens
        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_refresh_token = "refresh_xyz"
        settings.strava_expires_at = 9999999999
        await save_settings(db, settings)

        with patch(
            "easy_ride.api.strava_routes.upload_activity",
            new_callable=AsyncMock,
            return_value=98765,
        ):
            resp = await client.post(f"/api/strava/upload/{ride_id}")
        assert resp.status_code == 200
        assert resp.json()["upload_id"] == 98765

    async def test_upload_not_connected(self, client):
        ride_id = await _create_completed_ride(client)
        resp = await client.post(f"/api/strava/upload/{ride_id}")
        assert resp.status_code == 401

    async def test_upload_ride_not_found(self, client):
        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_expires_at = 9999999999
        await save_settings(db, settings)

        resp = await client.post("/api/strava/upload/nonexistent")
        assert resp.status_code == 404

    async def test_upload_duplicate_409(self, client):
        ride_id = await _create_completed_ride(client)

        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_refresh_token = "refresh_xyz"
        settings.strava_expires_at = 9999999999
        await save_settings(db, settings)

        # Set strava_activity_id to simulate already uploaded
        from easy_ride.db import set_ride_strava_activity
        await set_ride_strava_activity(db, ride_id, 12345)

        resp = await client.post(f"/api/strava/upload/{ride_id}")
        assert resp.status_code == 409

    async def test_upload_incomplete_ride_400(self, client):
        route_id = await _upload_route(client)
        resp = await client.post(
            "/api/rides",
            json={"route_id": route_id, "use_simulator": True},
        )
        ride_id = resp.json()["id"]

        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_expires_at = 9999999999
        await save_settings(db, settings)

        # Ride is active, not completed — need to stop engine and check from DB
        # Actually, fetch_ride on active engine will get live data which is ACTIVE status
        resp = await client.post(f"/api/strava/upload/{ride_id}")
        assert resp.status_code == 400

        await client.patch(f"/api/rides/{ride_id}/stop")


class TestStravaUploadStatus:
    async def test_poll_status(self, client):
        ride_id = await _create_completed_ride(client)

        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_refresh_token = "refresh_xyz"
        settings.strava_expires_at = 9999999999
        await save_settings(db, settings)

        mock_result = {
            "id": 98765,
            "status": "Your activity is ready.",
            "activity_id": 12345678,
            "error": None,
        }
        with patch(
            "easy_ride.api.strava_routes.poll_upload_status",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.get(
                f"/api/strava/upload/{ride_id}/status?upload_id=98765"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["activity_id"] == 12345678

        # Verify activity_id was saved on the ride
        from easy_ride.db import fetch_ride
        ride = await fetch_ride(db, ride_id)
        assert ride.strava_activity_id == 12345678

    async def test_poll_still_processing(self, client):
        ride_id = await _create_completed_ride(client)

        db = client._transport.app.state.db
        settings = await get_settings(db)
        settings.strava_access_token = "access_abc"
        settings.strava_expires_at = 9999999999
        await save_settings(db, settings)

        mock_result = {
            "id": 98765,
            "status": "Your activity is still being processed.",
            "activity_id": None,
            "error": None,
        }
        with patch(
            "easy_ride.api.strava_routes.poll_upload_status",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.get(
                f"/api/strava/upload/{ride_id}/status?upload_id=98765"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["activity_id"] is None


class TestStravaRideMetadata:
    async def test_ride_includes_strava_activity_id(self, client):
        ride_id = await _create_completed_ride(client)

        # Initially null
        resp = await client.get(f"/api/rides/{ride_id}")
        assert resp.json()["strava_activity_id"] is None

        # Set it
        db = client._transport.app.state.db
        from easy_ride.db import set_ride_strava_activity
        await set_ride_strava_activity(db, ride_id, 12345)

        resp = await client.get(f"/api/rides/{ride_id}")
        assert resp.json()["strava_activity_id"] == 12345

    async def test_ride_list_includes_strava_activity_id(self, client):
        ride_id = await _create_completed_ride(client)

        db = client._transport.app.state.db
        from easy_ride.db import set_ride_strava_activity
        await set_ride_strava_activity(db, ride_id, 99999)

        resp = await client.get("/api/rides")
        rides = resp.json()["rides"]
        matching = [r for r in rides if r["id"] == ride_id]
        assert len(matching) == 1
        assert matching[0]["strava_activity_id"] == 99999
