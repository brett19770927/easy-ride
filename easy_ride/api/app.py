from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from easy_ride.config import Config
from easy_ride.db import connect_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    config: Config = app.state.config
    config.ensure_dirs()
    db = await connect_db(config.db_path)
    await init_db(db)
    app.state.db = db
    yield
    await db.close()


def create_app(config: Config | None = None) -> FastAPI:
    if config is None:
        config = Config()

    app = FastAPI(title="Easy Ride", version="0.1.0", lifespan=lifespan)
    app.state.config = config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from easy_ride.api.routes import router
    from easy_ride.api.ride_routes import router as ride_router
    from easy_ride.api.device_routes import router as device_router
    from easy_ride.api.settings_routes import router as settings_router
    from easy_ride.api.profile_routes import router as profile_router
    from easy_ride.api.strava_routes import router as strava_router

    app.include_router(router)
    app.include_router(ride_router)
    app.include_router(device_router)
    app.include_router(settings_router)
    app.include_router(profile_router)
    app.include_router(strava_router)

    return app


def run() -> None:
    config = Config()
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port)
