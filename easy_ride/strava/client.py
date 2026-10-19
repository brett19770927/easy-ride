from __future__ import annotations

import time

import httpx

from easy_ride.exceptions import StravaAuthError, StravaUploadError

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_UPLOAD_URL = "https://www.strava.com/api/v3/uploads"


def build_authorize_url(client_id: str, redirect_uri: str) -> str:
    """Build the Strava OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "activity:write",
        "approval_prompt": "auto",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{STRAVA_AUTH_URL}?{qs}"


async def exchange_token(
    client_id: str,
    client_secret: str,
    code: str,
) -> dict:
    """Exchange an authorization code for access + refresh tokens.

    Returns dict with keys: access_token, refresh_token, expires_at.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise StravaAuthError(
                f"Token exchange failed ({resp.status_code}): {resp.text}"
            )
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": data["expires_at"],
        }


async def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    """Refresh an expired access token.

    Returns dict with keys: access_token, refresh_token, expires_at.
    Strava rotates the refresh token on each call — always save the new one.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            raise StravaAuthError(
                f"Token refresh failed ({resp.status_code}): {resp.text}"
            )
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": data["expires_at"],
        }


def token_is_expired(expires_at: int) -> bool:
    """Check if a token is expired (with 60s safety buffer)."""
    return time.time() >= (expires_at - 60)


async def upload_activity(
    access_token: str,
    tcx_data: str,
    name: str,
    sport_type: str = "Ride",
    trainer: bool = True,
) -> int:
    """Upload a TCX file to Strava and return the upload_id.

    Raises StravaUploadError on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            STRAVA_UPLOAD_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            files={"file": ("ride.tcx", tcx_data.encode("utf-8"), "application/xml")},
            data={
                "data_type": "tcx",
                "name": name,
                "sport_type": sport_type,
                "trainer": "1" if trainer else "0",
            },
        )
        if resp.status_code not in (200, 201):
            raise StravaUploadError(
                f"Upload failed ({resp.status_code}): {resp.text}",
                status_code=resp.status_code,
            )
        return resp.json()["id"]


async def poll_upload_status(
    access_token: str,
    upload_id: int,
) -> dict:
    """Check the status of a pending upload.

    Returns dict with keys: id, status, activity_id, error.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{STRAVA_UPLOAD_URL}/{upload_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            raise StravaUploadError(
                f"Status check failed ({resp.status_code}): {resp.text}",
                status_code=resp.status_code,
            )
        data = resp.json()
        return {
            "id": data["id"],
            "status": data["status"],
            "activity_id": data.get("activity_id"),
            "error": data.get("error"),
        }
