from __future__ import annotations

import uuid

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from easy_ride.db import (
    delete_profile,
    delete_ride,
    delete_route,
    fetch_profile,
    fetch_ride,
    fetch_route,
    get_settings,
    insert_profile,
    insert_route,
    list_profiles,
    list_rides,
    list_routes,
    save_settings,
    set_default_profile,
    update_profile,
)
from easy_ride.exceptions import (
    GPXParseError,
    ProfileNotFoundError,
    RideNotFoundError,
    RouteNotFoundError,
    RouteProcessingError,
)
from easy_ride.gpx.processor import process_gpx
from easy_ride.models import RideStatus, TrainerProfile, TrainerType

from easy_ride.api.ride_routes import _active_engines, _build_devices_from_profile
from easy_ride.ride.engine import RideEngine
from easy_ride.db import insert_ride, get_default_profile, fetch_profile as db_fetch_profile
from easy_ride.ble.simulator import SimulatedTrainer, SimulatedHRM
from easy_ride.ble.classic_adapter import ClassicTrainerAdapter
from easy_ride.ble.simulator import SimulatedSpeedCadenceSensor, SimulatedPowerMeter

router = APIRouter()


def _render(request: Request, template: str, context: dict | None = None):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, template, context or {})


# --- Dashboard ---

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = request.app.state.db
    routes = await list_routes(db)
    rides = await list_rides(db)
    return _render(request, "dashboard.html", {
        "routes": routes[:5],
        "rides": rides[:5],
    })


# --- Routes ---

@router.get("/routes", response_class=HTMLResponse)
async def routes_page(request: Request):
    db = request.app.state.db
    routes = await list_routes(db)
    return _render(request, "routes.html", {
        "routes": routes,
        "error": None,
    })


@router.post("/routes/upload")
async def upload_route(request: Request, file: UploadFile, name: str = Form("")):
    db = request.app.state.db
    content = await file.read()
    try:
        gpx_text = content.decode("utf-8")
    except UnicodeDecodeError:
        routes = await list_routes(db)
        return _render(request, "routes.html", {
            "routes": routes,
            "error": "File must be valid UTF-8",
        })

    filename = file.filename or ""
    try:
        route = process_gpx(gpx_text, name=name or "", filename=filename)
    except (GPXParseError, RouteProcessingError) as e:
        routes = await list_routes(db)
        return _render(request, "routes.html", {
            "routes": routes,
            "error": str(e),
        })

    await insert_route(db, route)
    return RedirectResponse(f"/routes/{route.id}", status_code=303)


@router.get("/routes/{route_id}", response_class=HTMLResponse)
async def route_detail(request: Request, route_id: str):
    db = request.app.state.db
    try:
        route = await fetch_route(db, route_id)
    except RouteNotFoundError:
        raise HTTPException(status_code=404, detail="Route not found")
    return _render(request, "route_detail.html", {"route": route})


@router.post("/routes/{route_id}/delete")
async def delete_route_page(request: Request, route_id: str):
    db = request.app.state.db
    try:
        await delete_route(db, route_id)
    except RouteNotFoundError:
        raise HTTPException(status_code=404, detail="Route not found")
    return RedirectResponse("/routes", status_code=303)


# --- Rides ---

@router.get("/ride/start", response_class=HTMLResponse)
async def ride_start_page(request: Request, route_id: str = ""):
    db = request.app.state.db
    route = None
    if route_id:
        try:
            route = await fetch_route(db, route_id)
        except RouteNotFoundError:
            raise HTTPException(status_code=404, detail="Route not found")
    profiles = await list_profiles(db)
    return _render(request, "ride_start.html", {
        "route_id": route_id,
        "route": route,
        "profiles": profiles,
        "error": None,
    })


@router.post("/ride/start")
async def start_ride_page(
    request: Request,
    route_id: str = Form(""),
    mode: str = Form("simulator_smart"),
):
    db = request.app.state.db

    if not route_id:
        raise HTTPException(status_code=400, detail="route_id is required")

    try:
        route = await fetch_route(db, route_id)
    except RouteNotFoundError:
        raise HTTPException(status_code=404, detail="Route not found")

    settings = await get_settings(db)

    if mode == "simulator_smart":
        trainer = SimulatedTrainer(ftp=settings.ftp, weight=settings.weight)
        hrm = SimulatedHRM()
        await trainer.connect()
        await hrm.connect()
    elif mode == "simulator_classic":
        speed_sensor = SimulatedSpeedCadenceSensor()
        pm = SimulatedPowerMeter(ftp=settings.ftp)
        trainer = ClassicTrainerAdapter(speed_sensor=speed_sensor, power_meter=pm)
        hrm = SimulatedHRM()
        await trainer.connect()
        await hrm.connect()
    elif mode.startswith("profile_"):
        profile_id = mode[len("profile_"):]
        try:
            profile = await db_fetch_profile(db, profile_id)
        except ProfileNotFoundError:
            profiles = await list_profiles(db)
            return _render(request, "ride_start.html", {
                "route_id": route_id,
                "route": route,
                "profiles": profiles,
                "error": "Profile not found",
            })
        trainer, hrm = await _build_devices_from_profile(profile, settings)
    else:
        raise HTTPException(status_code=400, detail="Invalid mode")

    engine = RideEngine(
        route=route, trainer=trainer, hrm=hrm,
        ftp=settings.ftp, rider_mass=settings.weight,
    )
    ride = await engine.start()
    await insert_ride(db, ride)
    _active_engines[engine.ride_id] = engine

    return RedirectResponse(f"/ride/{engine.ride_id}", status_code=303)


@router.get("/ride/{ride_id}", response_class=HTMLResponse)
async def ride_page(request: Request, ride_id: str):
    db = request.app.state.db
    # Check if active
    engine = _active_engines.get(ride_id)
    if engine:
        ride = engine._to_ride()
        return _render(request, "ride_active.html", {"ride": ride})
    # Completed/historical ride
    try:
        ride = await fetch_ride(db, ride_id)
    except RideNotFoundError:
        raise HTTPException(status_code=404, detail="Ride not found")
    return _render(request, "ride_detail.html", {"ride": ride})


@router.get("/rides", response_class=HTMLResponse)
async def rides_page(request: Request):
    db = request.app.state.db
    rides = await list_rides(db)
    return _render(request, "rides.html", {"rides": rides})


@router.post("/ride/{ride_id}/delete")
async def delete_ride_page(request: Request, ride_id: str):
    db = request.app.state.db
    engine = _active_engines.pop(ride_id, None)
    if engine and engine.status in (RideStatus.ACTIVE, RideStatus.PAUSED):
        await engine.stop()
    try:
        await delete_ride(db, ride_id)
    except RideNotFoundError:
        raise HTTPException(status_code=404, detail="Ride not found")
    return RedirectResponse("/rides", status_code=303)


# --- Settings ---

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, success: bool = False):
    db = request.app.state.db
    settings = await get_settings(db)
    config = request.app.state.config

    strava_connected = settings.strava_access_token is not None
    strava_expired = False
    if strava_connected and settings.strava_expires_at:
        from easy_ride.strava.client import token_is_expired
        strava_expired = token_is_expired(settings.strava_expires_at)

    strava_connect_url = ""
    if config.strava_configured and not strava_connected:
        from easy_ride.strava.client import build_authorize_url
        callback_url = f"http://{config.host}:{config.port}/api/strava/callback"
        strava_connect_url = build_authorize_url(config.strava_client_id, callback_url)

    return _render(request, "settings.html", {
        "settings": settings,
        "strava_connected": strava_connected,
        "strava_expired": strava_expired,
        "strava_configured": config.strava_configured,
        "strava_connect_url": strava_connect_url,
        "success": success,
    })


@router.post("/settings")
async def save_settings_page(
    request: Request,
    ftp: int = Form(...),
    weight: float = Form(...),
    elevation_smoothing_window: int = Form(5),
):
    db = request.app.state.db
    settings = await get_settings(db)
    settings.ftp = ftp
    settings.weight = weight
    settings.elevation_smoothing_window = elevation_smoothing_window
    await save_settings(db, settings)
    return RedirectResponse("/settings?success=true", status_code=303)


# --- Profiles ---

@router.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request):
    db = request.app.state.db
    profiles = await list_profiles(db)
    return _render(request, "profiles.html", {"profiles": profiles})


@router.get("/profiles/new", response_class=HTMLResponse)
async def profile_new_page(request: Request):
    return _render(request, "profile_form.html", {
        "profile": None,
        "error": None,
    })


@router.post("/profiles/new")
async def create_profile_page(
    request: Request,
    name: str = Form(""),
    trainer_type: str = Form("smart"),
    trainer_address: str = Form(""),
    speed_sensor_address: str = Form(""),
    power_meter_address: str = Form(""),
    hrm_address: str = Form(""),
    resistance_factor: float = Form(20.0),
    wheel_circumference: float = Form(2.105),
    is_default: str = Form(""),
):
    db = request.app.state.db
    try:
        tt = TrainerType(trainer_type)
    except ValueError:
        return _render(request, "profile_form.html", {
            "profile": None,
            "error": f"Invalid trainer type: {trainer_type}",
        })

    profile = TrainerProfile(
        id=str(uuid.uuid4()),
        name=name,
        trainer_type=tt,
        trainer_address=trainer_address or None,
        speed_sensor_address=speed_sensor_address or None,
        power_meter_address=power_meter_address or None,
        hrm_address=hrm_address or None,
        resistance_factor=resistance_factor,
        wheel_circumference=wheel_circumference,
        is_default=is_default == "true",
    )
    if profile.is_default:
        for existing in await list_profiles(db):
            if existing.is_default:
                existing.is_default = False
                await update_profile(db, existing)
    await insert_profile(db, profile)
    return RedirectResponse("/profiles", status_code=303)


@router.get("/profiles/{profile_id}/edit", response_class=HTMLResponse)
async def profile_edit_page(request: Request, profile_id: str):
    db = request.app.state.db
    try:
        profile = await fetch_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _render(request, "profile_form.html", {
        "profile": {
            "id": profile.id,
            "name": profile.name,
            "trainer_type": profile.trainer_type.value,
            "trainer_address": profile.trainer_address,
            "speed_sensor_address": profile.speed_sensor_address,
            "power_meter_address": profile.power_meter_address,
            "hrm_address": profile.hrm_address,
            "resistance_factor": profile.resistance_factor,
            "wheel_circumference": profile.wheel_circumference,
            "is_default": profile.is_default,
        },
        "error": None,
    })


@router.post("/profiles/{profile_id}/edit")
async def update_profile_page(
    request: Request,
    profile_id: str,
    name: str = Form(""),
    trainer_type: str = Form("smart"),
    trainer_address: str = Form(""),
    speed_sensor_address: str = Form(""),
    power_meter_address: str = Form(""),
    hrm_address: str = Form(""),
    resistance_factor: float = Form(20.0),
    wheel_circumference: float = Form(2.105),
    is_default: str = Form(""),
):
    db = request.app.state.db
    try:
        await fetch_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        tt = TrainerType(trainer_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid trainer type: {trainer_type}")

    updated = TrainerProfile(
        id=profile_id,
        name=name,
        trainer_type=tt,
        trainer_address=trainer_address or None,
        speed_sensor_address=speed_sensor_address or None,
        power_meter_address=power_meter_address or None,
        hrm_address=hrm_address or None,
        resistance_factor=resistance_factor,
        wheel_circumference=wheel_circumference,
        is_default=is_default == "true",
    )
    if updated.is_default:
        await set_default_profile(db, profile_id)
    await update_profile(db, updated)
    return RedirectResponse("/profiles", status_code=303)


@router.post("/profiles/{profile_id}/delete")
async def delete_profile_page(request: Request, profile_id: str):
    db = request.app.state.db
    try:
        await delete_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found")
    return RedirectResponse("/profiles", status_code=303)


# --- Devices ---

@router.get("/devices", response_class=HTMLResponse)
async def devices_page(request: Request):
    return _render(request, "devices.html", {
        "devices": [],
        "scanned": False,
        "error": None,
    })


@router.post("/devices/scan", response_class=HTMLResponse)
async def scan_devices_page(request: Request):
    try:
        from easy_ride.ble.scanner import scan_for_devices
        devices = await scan_for_devices()
        return _render(request, "devices.html", {
            "devices": devices,
            "scanned": True,
            "error": None,
        })
    except ImportError:
        return _render(request, "devices.html", {
            "devices": [],
            "scanned": True,
            "error": "BLE scanning not available — bleak not installed",
        })
    except Exception as e:
        return _render(request, "devices.html", {
            "devices": [],
            "scanned": True,
            "error": f"BLE scan failed: {e}",
        })
