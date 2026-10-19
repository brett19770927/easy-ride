from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    data_dir: Path = Path.home() / "easy_ride_data"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    strava_client_id: str = ""
    strava_client_secret: str = ""

    def __post_init__(self) -> None:
        if not self.strava_client_id:
            self.strava_client_id = os.environ.get("STRAVA_CLIENT_ID", "")
        if not self.strava_client_secret:
            self.strava_client_secret = os.environ.get("STRAVA_CLIENT_SECRET", "")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "easy_ride.db"

    @property
    def strava_configured(self) -> bool:
        return bool(self.strava_client_id and self.strava_client_secret)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
