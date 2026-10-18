from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request, UploadFile, HTTPException

from easy_ride.api.schemas import (
    RouteDetailResponse,
    RouteListResponse,
    RouteMetadataResponse,
    RoutePointResponse,
    RouteStatsResponse,
)
from easy_ride.exceptions import GPXParseError, RouteNotFoundError, RouteProcessingError
from easy_ride.gpx.processor import process_gpx
from easy_ride.db import delete_route, fetch_route, insert_route, list_routes

router = APIRouter(prefix="/api")


def _route_to_metadata(route) -> RouteMetadataResponse:
    return RouteMetadataResponse(
        id=route.id,
        name=route.name,
        source_filename=route.source_filename,
        created_at=route.created_at,
        stats=RouteStatsResponse(**asdict(route.stats)),
    )


def _route_to_detail(route) -> RouteDetailResponse:
    return RouteDetailResponse(
        id=route.id,
        name=route.name,
        source_filename=route.source_filename,
        created_at=route.created_at,
        stats=RouteStatsResponse(**asdict(route.stats)),
        points=[RoutePointResponse(**asdict(p)) for p in route.points],
    )


@router.post("/routes", status_code=201, response_model=RouteMetadataResponse)
async def upload_route(request: Request, file: UploadFile):
    content = await file.read()
    try:
        gpx_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be valid UTF-8")

    filename = file.filename or ""
    try:
        route = process_gpx(gpx_text, filename=filename)
    except (GPXParseError, RouteProcessingError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = request.app.state.db
    await insert_route(db, route)
    return _route_to_metadata(route)


@router.get("/routes", response_model=RouteListResponse)
async def get_routes(request: Request):
    db = request.app.state.db
    routes = await list_routes(db)
    return RouteListResponse(routes=[_route_to_metadata(r) for r in routes])


@router.get("/routes/{route_id}", response_model=RouteDetailResponse)
async def get_route(request: Request, route_id: str):
    db = request.app.state.db
    try:
        route = await fetch_route(db, route_id)
    except RouteNotFoundError:
        raise HTTPException(status_code=404, detail=f"Route not found: {route_id}")
    return _route_to_detail(route)


@router.delete("/routes/{route_id}", status_code=204)
async def remove_route(request: Request, route_id: str):
    db = request.app.state.db
    try:
        await delete_route(db, route_id)
    except RouteNotFoundError:
        raise HTTPException(status_code=404, detail=f"Route not found: {route_id}")
