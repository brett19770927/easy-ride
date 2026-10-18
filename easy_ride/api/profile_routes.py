from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from easy_ride.api.schemas import (
    TrainerProfileListResponse,
    TrainerProfileRequest,
    TrainerProfileResponse,
)
from easy_ride.db import (
    delete_profile,
    fetch_profile,
    insert_profile,
    list_profiles,
    set_default_profile,
    update_profile,
)
from easy_ride.exceptions import ProfileNotFoundError
from easy_ride.models import TrainerProfile, TrainerType

router = APIRouter(prefix="/api")


def _profile_to_response(p: TrainerProfile) -> TrainerProfileResponse:
    return TrainerProfileResponse(
        id=p.id,
        name=p.name,
        trainer_type=p.trainer_type.value,
        trainer_address=p.trainer_address,
        speed_sensor_address=p.speed_sensor_address,
        cadence_sensor_address=p.cadence_sensor_address,
        power_meter_address=p.power_meter_address,
        hrm_address=p.hrm_address,
        resistance_factor=p.resistance_factor,
        wheel_circumference=p.wheel_circumference,
        is_default=p.is_default,
    )


@router.post("/profiles", status_code=201, response_model=TrainerProfileResponse)
async def create_profile(request: Request, body: TrainerProfileRequest):
    db = request.app.state.db
    try:
        trainer_type = TrainerType(body.trainer_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trainer_type: {body.trainer_type}. "
            f"Must be one of: smart, classic, power_meter_only",
        )
    profile = TrainerProfile(
        id=str(uuid.uuid4()),
        name=body.name,
        trainer_type=trainer_type,
        trainer_address=body.trainer_address,
        speed_sensor_address=body.speed_sensor_address,
        cadence_sensor_address=body.cadence_sensor_address,
        power_meter_address=body.power_meter_address,
        hrm_address=body.hrm_address,
        resistance_factor=body.resistance_factor,
        wheel_circumference=body.wheel_circumference,
        is_default=body.is_default,
    )
    if body.is_default:
        # Clear other defaults before insert
        for existing in await list_profiles(db):
            if existing.is_default:
                existing.is_default = False
                await update_profile(db, existing)
    await insert_profile(db, profile)
    return _profile_to_response(profile)


@router.get("/profiles", response_model=TrainerProfileListResponse)
async def get_profiles(request: Request):
    db = request.app.state.db
    profiles = await list_profiles(db)
    return TrainerProfileListResponse(
        profiles=[_profile_to_response(p) for p in profiles]
    )


@router.get("/profiles/{profile_id}", response_model=TrainerProfileResponse)
async def get_profile(request: Request, profile_id: str):
    db = request.app.state.db
    try:
        profile = await fetch_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")
    return _profile_to_response(profile)


@router.put("/profiles/{profile_id}", response_model=TrainerProfileResponse)
async def update_profile_endpoint(
    request: Request, profile_id: str, body: TrainerProfileRequest,
):
    db = request.app.state.db
    try:
        trainer_type = TrainerType(body.trainer_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trainer_type: {body.trainer_type}")
    try:
        existing = await fetch_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")
    updated = TrainerProfile(
        id=profile_id,
        name=body.name,
        trainer_type=trainer_type,
        trainer_address=body.trainer_address,
        speed_sensor_address=body.speed_sensor_address,
        cadence_sensor_address=body.cadence_sensor_address,
        power_meter_address=body.power_meter_address,
        hrm_address=body.hrm_address,
        resistance_factor=body.resistance_factor,
        wheel_circumference=body.wheel_circumference,
        is_default=body.is_default,
    )
    if body.is_default:
        await set_default_profile(db, profile_id)
    await update_profile(db, updated)
    return _profile_to_response(updated)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile_endpoint(request: Request, profile_id: str):
    db = request.app.state.db
    try:
        await delete_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_id}")
