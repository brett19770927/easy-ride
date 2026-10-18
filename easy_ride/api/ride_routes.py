from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from easy_ride.api.schemas import (
    RideDetailResponse,
    RideListResponse,
    RideMetadataResponse,
    RideSampleResponse,
    RideStatsResponse,
    StartRideRequest,
)
from easy_ride.ble.simulator import SimulatedHRM, SimulatedTrainer
from easy_ride.db import (
    delete_ride,
    fetch_ride,
    fetch_route,
    get_settings,
    insert_ride,
    list_rides,
    update_ride_status,
)
from easy_ride.exceptions import RideNotFoundError, RideStateError, RouteNotFoundError
from easy_ride.models import RideStatus
from easy_ride.ride.engine import RideEngine

router = APIRouter(prefix="/api")

# Active ride engines keyed by ride_id
_active_engines: dict[str, RideEngine] = {}


def _ride_stats_response(stats) -> RideStatsResponse | None:
    if stats is None:
        return None
    return RideStatsResponse(
        duration=stats.duration,
        distance=stats.distance,
        avg_speed=stats.avg_speed,
        max_speed=stats.max_speed,
        avg_power=stats.avg_power,
        max_power=stats.max_power,
        avg_cadence=stats.avg_cadence,
        avg_heart_rate=stats.avg_heart_rate,
        total_ascent=stats.total_ascent,
    )


def _ride_to_metadata(ride) -> RideMetadataResponse:
    return RideMetadataResponse(
        id=ride.id,
        route_id=ride.route_id,
        status=ride.status.value if hasattr(ride.status, "value") else ride.status,
        started_at=ride.started_at,
        finished_at=ride.finished_at,
        stats=_ride_stats_response(ride.stats),
    )


def _ride_to_detail(ride) -> RideDetailResponse:
    return RideDetailResponse(
        id=ride.id,
        route_id=ride.route_id,
        status=ride.status.value if hasattr(ride.status, "value") else ride.status,
        started_at=ride.started_at,
        finished_at=ride.finished_at,
        stats=_ride_stats_response(ride.stats),
        samples=[
            RideSampleResponse(
                timestamp=s.timestamp,
                distance=s.distance,
                speed=s.speed,
                power=s.power,
                cadence=s.cadence,
                heart_rate=s.heart_rate,
                route_point_idx=s.route_point_idx,
            )
            for s in ride.samples
        ],
    )


@router.post("/rides", status_code=201, response_model=RideMetadataResponse)
async def start_ride(request: Request, body: StartRideRequest):
    db = request.app.state.db
    try:
        route = await fetch_route(db, body.route_id)
    except RouteNotFoundError:
        raise HTTPException(status_code=404, detail=f"Route not found: {body.route_id}")

    settings = await get_settings(db)

    if body.use_simulator:
        trainer = SimulatedTrainer(ftp=settings.ftp, weight=settings.weight)
        hrm = SimulatedHRM()
        await trainer.connect()
        await hrm.connect()
    else:
        raise HTTPException(
            status_code=501,
            detail="Real BLE device support not yet implemented — use use_simulator=true",
        )

    engine = RideEngine(route=route, trainer=trainer, hrm=hrm, ftp=settings.ftp)
    ride = await engine.start()

    # Persist initial ride record
    await insert_ride(db, ride)
    _active_engines[engine.ride_id] = engine

    return _ride_to_metadata(ride)


@router.get("/rides", response_model=RideListResponse)
async def get_rides(request: Request):
    db = request.app.state.db
    rides = await list_rides(db)
    return RideListResponse(rides=[_ride_to_metadata(r) for r in rides])


@router.get("/rides/{ride_id}", response_model=RideDetailResponse)
async def get_ride(request: Request, ride_id: str):
    db = request.app.state.db
    # Check active engine first for live data
    engine = _active_engines.get(ride_id)
    if engine:
        ride = engine._to_ride()
        return _ride_to_detail(ride)
    try:
        ride = await fetch_ride(db, ride_id)
    except RideNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ride not found: {ride_id}")
    return _ride_to_detail(ride)


@router.delete("/rides/{ride_id}", status_code=204)
async def remove_ride(request: Request, ride_id: str):
    db = request.app.state.db
    # Stop active engine if running
    engine = _active_engines.pop(ride_id, None)
    if engine and engine.status in (RideStatus.ACTIVE, RideStatus.PAUSED):
        await engine.stop()
    try:
        await delete_ride(db, ride_id)
    except RideNotFoundError:
        raise HTTPException(status_code=404, detail=f"Ride not found: {ride_id}")


@router.patch("/rides/{ride_id}/pause", response_model=RideMetadataResponse)
async def pause_ride(request: Request, ride_id: str):
    engine = _active_engines.get(ride_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"No active ride: {ride_id}")
    try:
        ride = await engine.pause()
    except RideStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db = request.app.state.db
    await update_ride_status(db, ride_id, ride.status)
    return _ride_to_metadata(ride)


@router.patch("/rides/{ride_id}/resume", response_model=RideMetadataResponse)
async def resume_ride(request: Request, ride_id: str):
    engine = _active_engines.get(ride_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"No active ride: {ride_id}")
    try:
        ride = await engine.resume()
    except RideStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    db = request.app.state.db
    await update_ride_status(db, ride_id, ride.status)
    return _ride_to_metadata(ride)


@router.patch("/rides/{ride_id}/stop", response_model=RideMetadataResponse)
async def stop_ride(request: Request, ride_id: str):
    engine = _active_engines.pop(ride_id, None)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"No active ride: {ride_id}")
    try:
        ride = await engine.stop()
    except RideStateError as e:
        _active_engines[ride_id] = engine
        raise HTTPException(status_code=409, detail=str(e))
    db = request.app.state.db
    await update_ride_status(
        db, ride_id, ride.status,
        finished_at=ride.finished_at,
        stats=ride.stats,
        samples=ride.samples,
    )
    return _ride_to_metadata(ride)


@router.get("/rides/{ride_id}/live")
async def live_ride_stream(request: Request, ride_id: str):
    engine = _active_engines.get(ride_id)
    if engine is None:
        raise HTTPException(status_code=404, detail=f"No active ride: {ride_id}")

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def on_event(event: dict[str, Any]) -> None:
        queue.put_nowait(event)

    engine.subscribe(on_event)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield {"event": event["type"], "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                if engine.status in (RideStatus.COMPLETED, RideStatus.CANCELLED):
                    break
        finally:
            engine.unsubscribe(on_event)

    return EventSourceResponse(event_generator())
