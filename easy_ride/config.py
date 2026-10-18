from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    data_dir: Path = Path.home() / "easy_ride_data"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "easy_ride.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
