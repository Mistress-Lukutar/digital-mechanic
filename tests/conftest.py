'''
File:   conftest.py
Brief:  Shared pytest fixtures for fleet tests and client tests.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

from pathlib import Path

import pytest

from mechanic.config import Settings
from mechanic.services.fleet import FleetStore

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def settings() -> Settings:
    """Application settings pointing at the committed data directory."""
    return Settings(
        _env_file=None,
        app_data_dir=REPO_ROOT / "data",
        manuals_dir=REPO_ROOT / "data" / "manuals",
    )


@pytest.fixture()
def fleet(settings: Settings) -> FleetStore:
    """Fleet store initialised from the committed data directory."""
    return FleetStore(settings.app_data_dir)
