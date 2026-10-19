from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from easy_ride.exceptions import StravaAuthError, StravaUploadError
from easy_ride.strava.client import (
    build_authorize_url,
    exchange_token,
    poll_upload_status,
    refresh_access_token,
    token_is_expired,
    upload_activity,
)


def _mock_response(status_code: int, json_data: dict | None = None, text: str = ""):
    resp = httpx.Response(status_code, text=text)
    if json_data is not None:
        resp = httpx.Response(
            status_code,
            json=json_data,
            request=httpx.Request("POST", "https://example.com"),
        )
    else:
        resp = httpx.Response(
            status_code,
            text=text,
            request=httpx.Request("POST", "https://example.com"),
        )
    return resp


class TestBuildAuthorizeUrl:
    def test_contains_client_id(self):
        url = build_authorize_url("my_id", "http://localhost/callback")
        assert "client_id=my_id" in url

    def test_contains_redirect_uri(self):
        url = build_authorize_url("my_id", "http://localhost/callback")
        assert "redirect_uri=http://localhost/callback" in url

    def test_has_activity_write_scope(self):
        url = build_authorize_url("my_id", "http://localhost/callback")
        assert "scope=activity:write" in url

    def test_starts_with_strava_url(self):
        url = build_authorize_url("my_id", "http://localhost/callback")
        assert url.startswith("https://www.strava.com/oauth/authorize?")


class TestExchangeToken:
    async def test_successful_exchange(self):
        mock_resp = _mock_response(200, {
            "access_token": "access123",
            "refresh_token": "refresh456",
            "expires_at": 1700000000,
        })
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await exchange_token("id", "secret", "code123")
            assert result["access_token"] == "access123"
            assert result["refresh_token"] == "refresh456"
            assert result["expires_at"] == 1700000000

    async def test_failed_exchange_raises(self):
        mock_resp = _mock_response(401, text="Unauthorized")
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(StravaAuthError):
                await exchange_token("id", "secret", "bad_code")


class TestRefreshToken:
    async def test_successful_refresh(self):
        mock_resp = _mock_response(200, {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
            "expires_at": 1700100000,
        })
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await refresh_access_token("id", "secret", "old_refresh")
            assert result["access_token"] == "new_access"
            assert result["refresh_token"] == "new_refresh"

    async def test_failed_refresh_raises(self):
        mock_resp = _mock_response(401, text="Bad refresh token")
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(StravaAuthError):
                await refresh_access_token("id", "secret", "bad_token")


class TestTokenExpiry:
    def test_expired_token(self):
        assert token_is_expired(int(time.time()) - 100) is True

    def test_valid_token(self):
        assert token_is_expired(int(time.time()) + 3600) is False

    def test_token_near_expiry_within_buffer(self):
        # Within 60s buffer — considered expired
        assert token_is_expired(int(time.time()) + 30) is True

    def test_token_just_outside_buffer(self):
        assert token_is_expired(int(time.time()) + 120) is False


class TestUploadActivity:
    async def test_successful_upload(self):
        mock_resp = _mock_response(201, {"id": 98765})
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            upload_id = await upload_activity("token", "<tcx/>", "My Ride")
            assert upload_id == 98765

    async def test_failed_upload_raises(self):
        mock_resp = _mock_response(400, text="Bad request")
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            with pytest.raises(StravaUploadError):
                await upload_activity("token", "<tcx/>", "My Ride")


class TestPollUploadStatus:
    async def test_processing_status(self):
        mock_resp = _mock_response(200, {
            "id": 98765,
            "status": "Your activity is still being processed.",
            "activity_id": None,
            "error": None,
        })
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await poll_upload_status("token", 98765)
            assert result["activity_id"] is None
            assert "processed" in result["status"]

    async def test_ready_with_activity_id(self):
        mock_resp = _mock_response(200, {
            "id": 98765,
            "status": "Your activity is ready.",
            "activity_id": 12345678,
            "error": None,
        })
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await poll_upload_status("token", 98765)
            assert result["activity_id"] == 12345678

    async def test_error_status(self):
        mock_resp = _mock_response(200, {
            "id": 98765,
            "status": "There was an error processing your activity.",
            "activity_id": None,
            "error": "duplicate of activity 111",
        })
        with patch("easy_ride.strava.client.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await poll_upload_status("token", 98765)
            assert result["error"] is not None
            assert "duplicate" in result["error"]
