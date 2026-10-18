from __future__ import annotations

from pathlib import Path

import pytest

from easy_ride.gpx.processor import process_gpx

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_loop_gpx() -> str:
    return (FIXTURES_DIR / "simple_loop.gpx").read_text()


@pytest.fixture
def mountain_climb_gpx() -> str:
    return (FIXTURES_DIR / "mountain_climb.gpx").read_text()


@pytest.fixture
def simple_loop_path() -> Path:
    return FIXTURES_DIR / "simple_loop.gpx"


@pytest.fixture
def mountain_climb_path() -> Path:
    return FIXTURES_DIR / "mountain_climb.gpx"


@pytest.fixture
def sample_route(simple_loop_gpx):
    return process_gpx(simple_loop_gpx, filename="simple_loop.gpx")
