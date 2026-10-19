# Easy Ride

Virtual cycling app that simulates GPX routes on smart/dumb trainers via BLE.

## Project Structure
Python package `easy_ride/` with submodules:
- `gpx/` — GPX parsing, geo math, elevation processing, route pipeline
- `ble/` — BLE device protocols, simulator, scanner, real BLE trainer/HRM, device factory
- `ride/` — Physics engine, stats collector, ride engine state machine
- `api/` — FastAPI app factory, REST endpoints, UI routes, Pydantic schemas
- `strava/` — Strava OAuth client, TCX generation, upload API
- `templates/` — Jinja2 HTML templates (base layout + 11 page templates)
- `static/` — CSS (`main.css`) and JS (`ride-live.js`)
- Top-level: models (dataclasses), exceptions, config, SQLite DB layer

## Stack
- Python 3.11+ (use `python3.13` for venv — system Python is 3.9)
- FastAPI + uvicorn, Jinja2, aiosqlite, python-multipart
- pycycling (FTMS/CPS/HRM BLE protocols), bleak (BLE scanning/connections)
- sse-starlette (Server-Sent Events for live ride data)
- httpx (Strava API client + test transport)
- Dev: pytest, pytest-asyncio, pytest-cov

## Setup
```
cd ~/projects/software/easy-ride
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Testing
- `pytest -v` — 307 tests across 20 test files
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
  - `/api/strava/connect` — GET returns Strava OAuth authorize URL
  - `/api/strava/callback?code=X` — GET handles OAuth redirect, stores tokens
  - `/api/strava/status` — GET check connection + token expiry
  - `/api/strava/disconnect` — POST clear stored tokens
  - `/api/strava/upload/{ride_id}` — POST generate TCX + upload to Strava
  - `/api/strava/upload/{ride_id}/status?upload_id=X` — GET poll upload status
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

## Strava Integration
- OAuth 2.0 flow: connect → callback → store tokens (access, refresh, expires_at)
- Token auto-refresh: `_ensure_valid_token()` checks expiry (60s buffer) and refreshes before API calls
- Strava rotates refresh tokens on each refresh — always save the new one immediately
- TCX generation: `generate_tcx(ride, route)` → XML string with trackpoints, position, power, HR, cadence
- Upload flow: generate TCX → POST multipart to Strava → poll upload status → save activity_id
- Guards: ride must be completed (400), not already uploaded (409), Strava connected (401), configured (400)
- Config: `STRAVA_CLIENT_ID` + `STRAVA_CLIENT_SECRET` env vars required

## Database
- Schema version 4 (auto-migrates from v1/v2/v3)
- Tables: routes, route_points, rides, ride_samples, user_settings, trainer_profiles, schema_version
- ride_samples has composite PK (ride_id, idx) with CASCADE delete
- Settings stored as key-value pairs, loaded into `UserSettings` dataclass
- Strava tokens stored in user_settings (strava_access_token, strava_refresh_token, strava_expires_at)
- rides.strava_activity_id tracks which rides have been uploaded

## BLE Device Factory
- `ble/factory.py` — creates BLE device objects from a `TrainerProfile`
- `validate_profile(profile)` — checks required addresses per trainer type
- `build_devices_from_profile(profile)` → `(trainer, hrm | None)` — instantiates but doesn't connect
- SMART → `FTMSTrainer`, CLASSIC → `BLESpeedCadenceSensor` + optional `BLEPowerMeter` → `ClassicTrainerAdapter`, POWER_METER_ONLY → `BLEPowerMeter` → `ClassicTrainerAdapter`
- `ProfileValidationError` in `exceptions.py` for missing required addresses
- `ride_routes._build_devices_from_profile()` calls factory, connects, handles errors (400/503)

## Web UI
- Server-rendered HTML via Jinja2 templates (no SPA, no JS framework)
- Templates in `easy_ride/templates/`, static files in `easy_ride/static/`
- `api/ui_routes.py` — all HTML page route handlers (no `/api` prefix)
- `api/app.py` mounts `Jinja2Templates` + `StaticFiles`, includes `ui_routes`

### UI Pages
| Path | Template | Purpose |
|------|----------|---------|
| `/` | `dashboard.html` | Recent routes + rides, quick actions |
| `/routes` | `routes.html` | Route list + GPX upload form |
| `/routes/{id}` | `route_detail.html` | Route stats, start ride link |
| `/ride/start` | `ride_start.html` | Mode selection (sim/profile) |
| `/ride/{id}` | `ride_active.html` or `ride_detail.html` | Active (SSE) or completed |
| `/rides` | `rides.html` | Ride history |
| `/settings` | `settings.html` | FTP, weight, Strava |
| `/profiles` | `profiles.html` | Profile list |
| `/profiles/new` | `profile_form.html` | Create profile |
| `/profiles/{id}/edit` | `profile_form.html` | Edit profile |
| `/devices` | `devices.html` | BLE scan |

### Accessibility
- Skip-to-content link on every page
- `<nav aria-label="Main navigation">` with `aria-current="page"`
- Landmark roles (`banner`, `main`, `contentinfo`)
- `aria-live="polite"` on live ride data and device scan results
- Screen reader announcements via `#live-announcer` (`.sr-only`, every 10th update)
- All form inputs have associated `<label>` elements
- `aria-describedby` for help text on device address fields
- 3px orange focus indicators, high-contrast colours

### Live Ride JavaScript
- `static/js/ride-live.js` — vanilla JS, no dependencies
- `EventSource` to `/api/rides/{id}/live` for real-time SSE data
- Updates `#live-power`, `#live-speed`, etc. on each `sample` event
- Periodic screen reader announcements (every 10th sample)
- Pause/resume/stop buttons via `fetch()` PATCH to API

## Testing
- 307 tests across 20 test files
- `tests/test_ble_factory.py` — 15 tests for device factory + validation
- `tests/test_ui.py` — 39 tests for all UI pages, accessibility checks, form submission

## Phases
- Phase 1 (complete): Project scaffold + GPX processing + API + DB
- Phase 2 (complete): BLE trainer integration, ride simulation, device protocols
- Phase 2.5 (complete): Classic/sensor trainer support, trainer profiles, virtual speed model
- Phase 3 (complete): Strava sync — OAuth, TCX export, upload + status polling, token auto-refresh
- Phase 4 (complete): Web UI (Jinja2 templates, accessible HTML) + real BLE device wiring
- Phase 5+: Real BLE hardware testing, mobile-responsive refinements
