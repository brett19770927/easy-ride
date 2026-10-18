from __future__ import annotations

from fastapi import APIRouter, Request

from easy_ride.api.schemas import SettingsResponse, SettingsUpdateRequest
from easy_ride.db import get_settings, save_settings
from easy_ride.models import UserSettings

router = APIRouter(prefix="/api")


@router.get("/settings", response_model=SettingsResponse)
async def get_user_settings(request: Request):
    db = request.app.state.db
    settings = await get_settings(db)
    return SettingsResponse(
        ftp=settings.ftp,
        weight=settings.weight,
        trainer_device_id=settings.trainer_device_id,
        hrm_device_id=settings.hrm_device_id,
        elevation_smoothing_window=settings.elevation_smoothing_window,
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(request: Request, body: SettingsUpdateRequest):
    db = request.app.state.db
    current = await get_settings(db)
    if body.ftp is not None:
        current.ftp = body.ftp
    if body.weight is not None:
        current.weight = body.weight
    if body.trainer_device_id is not None:
        current.trainer_device_id = body.trainer_device_id
    if body.hrm_device_id is not None:
        current.hrm_device_id = body.hrm_device_id
    if body.elevation_smoothing_window is not None:
        current.elevation_smoothing_window = body.elevation_smoothing_window
    await save_settings(db, current)
    return SettingsResponse(
        ftp=current.ftp,
        weight=current.weight,
        trainer_device_id=current.trainer_device_id,
        hrm_device_id=current.hrm_device_id,
        elevation_smoothing_window=current.elevation_smoothing_window,
    )
