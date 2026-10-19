from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from easy_ride.api.schemas import (
    StravaConnectResponse,
    StravaStatusResponse,
    StravaUploadResponse,
    StravaUploadStatusResponse,
)
from easy_ride.db import (
    clear_strava_tokens,
    fetch_ride,
    fetch_route,
    get_settings,
    save_settings,
    set_ride_strava_activity,
)
from easy_ride.exceptions import (
    RideNotFoundError,
    RouteNotFoundError,
    StravaAuthError,
    StravaUploadError,
)
from easy_ride.models import RideStatus, UserSettings
from easy_ride.strava.client import (
    build_authorize_url,
    exchange_token,
    poll_upload_status,
    refresh_access_token,
    token_is_expired,
    upload_activity,
)
from easy_ride.strava.tcx import generate_tcx

router = APIRouter(prefix="/api/strava")


def _require_strava_configured(request: Request) -> None:
    config = request.app.state.config
    if not config.strava_configured:
        raise HTTPException(
            status_code=400,
            detail="Strava not configured — set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET",
        )


@router.get("/connect", response_model=StravaConnectResponse)
async def strava_connect(request: Request):
    _require_strava_configured(request)
    config = request.app.state.config
    callback_url = f"http://{config.host}:{config.port}/api/strava/callback"
    url = build_authorize_url(config.strava_client_id, callback_url)
    return StravaConnectResponse(authorize_url=url)


@router.get("/callback")
async def strava_callback(request: Request, code: str):
    _require_strava_configured(request)
    config = request.app.state.config
    db = request.app.state.db
    try:
        tokens = await exchange_token(
            config.strava_client_id, config.strava_client_secret, code
        )
    except StravaAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    settings = await get_settings(db)
    settings.strava_access_token = tokens["access_token"]
    settings.strava_refresh_token = tokens["refresh_token"]
    settings.strava_expires_at = tokens["expires_at"]
    await save_settings(db, settings)
    return {"status": "connected"}


@router.get("/status", response_model=StravaStatusResponse)
async def strava_status(request: Request):
    db = request.app.state.db
    settings = await get_settings(db)
    connected = settings.strava_access_token is not None
    expired = False
    if connected and settings.strava_expires_at is not None:
        expired = token_is_expired(settings.strava_expires_at)
    return StravaStatusResponse(
        connected=connected,
        expires_at=settings.strava_expires_at,
        expired=expired,
    )


@router.post("/disconnect")
async def strava_disconnect(request: Request):
    db = request.app.state.db
    await clear_strava_tokens(db)
    return {"status": "disconnected"}


async def _ensure_valid_token(request: Request) -> str:
    """Return a valid access token, refreshing if expired."""
    db = request.app.state.db
    settings = await get_settings(db)

    if not settings.strava_access_token:
        raise HTTPException(
            status_code=401, detail="Not connected to Strava"
        )

    if settings.strava_expires_at and token_is_expired(settings.strava_expires_at):
        _require_strava_configured(request)
        config = request.app.state.config
        try:
            tokens = await refresh_access_token(
                config.strava_client_id,
                config.strava_client_secret,
                settings.strava_refresh_token,
            )
        except StravaAuthError as e:
            # Refresh failed — tokens are invalid
            await clear_strava_tokens(db)
            raise HTTPException(status_code=401, detail=str(e))

        settings.strava_access_token = tokens["access_token"]
        settings.strava_refresh_token = tokens["refresh_token"]
        settings.strava_expires_at = tokens["expires_at"]
        await save_settings(db, settings)

    return settings.strava_access_token


@router.post("/upload/{ride_id}", response_model=StravaUploadResponse)
async def strava_upload(request: Request, ride_id: str):
    _require_strava_configured(request)
    db = request.app.state.db

    try:
        ride = await fetch_ride(db, ride_id)
    except RideNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ride not found: {ride_id}")

    if ride.status != RideStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Ride is not completed")

    if ride.strava_activity_id is not None:
        raise HTTPException(
            status_code=409, detail="Ride already uploaded to Strava"
        )

    try:
        route = await fetch_route(db, ride.route_id)
    except RouteNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Route not found: {ride.route_id}"
        )

    access_token = await _ensure_valid_token(request)

    tcx_data = generate_tcx(ride, route)
    name = f"Easy Ride — {route.name}"

    try:
        upload_id = await upload_activity(access_token, tcx_data, name)
    except StravaUploadError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return StravaUploadResponse(upload_id=upload_id)


@router.get("/upload/{ride_id}/status", response_model=StravaUploadStatusResponse)
async def strava_upload_status(request: Request, ride_id: str, upload_id: int):
    db = request.app.state.db

    try:
        ride = await fetch_ride(db, ride_id)
    except RideNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ride not found: {ride_id}")

    access_token = await _ensure_valid_token(request)

    try:
        result = await poll_upload_status(access_token, upload_id)
    except StravaUploadError as e:
        raise HTTPException(status_code=502, detail=str(e))

    # If the activity is ready, save the activity_id on the ride
    if result.get("activity_id") and ride.strava_activity_id is None:
        await set_ride_strava_activity(db, ride_id, result["activity_id"])

    return StravaUploadStatusResponse(
        id=result["id"],
        status=result["status"],
        activity_id=result.get("activity_id"),
        error=result.get("error"),
    )
