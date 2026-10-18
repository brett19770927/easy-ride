# Easy Ride

Virtual cycling app that simulates GPX routes on smart/dumb trainers via BLE.

## Project Structure
Python package `easy_ride/` with four submodules:
- `gpx/` — GPX parsing, geo math, elevation processing, route pipeline
- `ble/` — BLE device protocols, simulator, scanner, real BLE trainer/HRM
- `ride/` — Physics engine, stats collector, ride engine state machine
- `api/` — FastAPI app factory, REST endpoints, Pydantic schemas
- Top-level: models (dataclasses), exceptions, config, SQLite DB layer

## Stack
- Python 3.11+ (use `python3.13` for venv — system Python is 3.9)
- FastAPI + uvicorn, aiosqlite, python-multipart
- pycycling (FTMS/CPS/HRM BLE protocols), bleak (BLE scanning/connections)
- sse-starlette (Server-Sent Events for live ride data)
- Dev: pytest, pytest-asyncio, pytest-cov, httpx

## Setup
```
cd ~/projects/software/easy-ride
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Testing
- `pytest -v` — tests across 18 test files
- Tests use `tmp_path` for isolated SQLite DBs
- API tests manually init DB since `ASGITransport` doesn't trigger ASGI lifespan
- GPX test fixtures in `tests/fixtures/` (simple_loop.gpx, mountain_climb.gpx)
- `asyncio_mode = "auto"` in pyproject.toml — no need for `@pytest.mark.asyncio`
- BLE/ride tests use `SimulatedTrainer` and `SimulatedHRM` — no hardware needed
- Simulator tests use `asyncio.sleep()` for timing (1Hz data generation)
- `conftest.py` has a shared `sample_route` fixture from simple_loop.gpx

## Running
- `easy-ride` — starts server on 0.0.0.0:8000
- API prefixes:
  - `/api/routes` — POST upload, GET list, GET/{id} detail, DELETE/{id}
  - `/api/rides` — POST start, GET list, GET/{id} detail, DELETE/{id}
  - `/api/rides/{id}/pause|resume|stop` — ride lifecycle control (PATCH)
  - `/api/rides/{id}/live` — SSE stream (real-time samples + stats)
  - `/api/devices/scan` — BLE device discovery
  - `/api/profiles` — POST create, GET list, GET/{id} detail, PUT/{id} update, DELETE/{id}
  - `/api/settings` — GET/PUT user settings (FTP, weight, device IDs)

## Conventions
- Domain models are plain `@dataclass` with `from __future__ import annotations`
- Pydantic schemas only in `api/schemas.py` — separate from domain models
- GPX processing is pure functions, no DB access — API layer persists results
- Exceptions in `exceptions.py` hierarchy under `EasyRideError`
- Config uses dataclass with `db_path` property derived from `data_dir`
- Package discovery explicitly includes only `easy_ride*` (excludes `data/`)

## Architecture: BLE + Ride Engine
- Abstract device interface via `typing.Protocol` (`TrainerDevice`, `HRMDevice`, `SpeedCadenceSensor`, `PowerMeterDevice`)
- Device types: TRAINER (FTMS smart), POWER_METER (CPS standalone), SPEED_CADENCE (CSC), HRM
- Real BLE (pycycling) and simulator both implement the same protocols
- `ClassicTrainerAdapter` wraps speed/cadence + optional power meter into TrainerDevice protocol
- Ride engine is a state machine: `idle → active ↔ paused → completed/cancelled`
- **Virtual speed model**: power → `speed_from_power(power, gradient, mass)` → distance (all trainer types)
- 1Hz main loop: drain device data → compute virtual speed → update distance → find route point → set gradient → collect sample → publish SSE
- Active engines stored in-memory in `api/ride_routes._active_engines`
- SSE live stream via `sse-starlette` with ping keepalive

## Trainer Profiles
- `TrainerProfile` dataclass: name, type (smart/classic/power_meter_only), device addresses, resistance_factor, wheel_circumference
- CRUD in `db.py`: insert/fetch/list/update/delete + default profile support
- API: `/api/profiles` — POST/GET/GET{id}/PUT{id}/DELETE{id}
- Ride start uses profile to build device chain (or simulator with `simulator_mode=smart|classic`)

## Database
- Schema version 3 (auto-migrates from v1/v2)
- Tables: routes, route_points, rides, ride_samples, user_settings, trainer_profiles, schema_version
- ride_samples has composite PK (ride_id, idx) with CASCADE delete
- Settings stored as key-value pairs, loaded into `UserSettings` dataclass

## Phases
- Phase 1 (complete): Project scaffold + GPX processing + API + DB
- Phase 2 (complete): BLE trainer integration, ride simulation, device protocols
- Phase 2.5 (complete): Classic/sensor trainer support, trainer profiles, virtual speed model
- Phase 3+: Strava sync, real BLE hardware testing, UI
