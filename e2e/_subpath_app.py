'''
File:   _subpath_app.py
Brief:  FastAPI wrapper that mounts real app at /mech.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Reads configuration from environment variables prefixed with E2E_ and builds
a Settings instance explicitly (no .env file). Resets module-level singletons
in api.deps so that the mounted sub-app gets a fresh hub and settings store.
The bootstrap_admin call is a no-op because conftest seeds the admin user
before starting this process.
'''

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

# Reset module singletons before building (mirrors tests/integration/test_api.py).
from mechanic.api import deps as api_deps  # noqa: E402

api_deps._hub = None  # type: ignore[attr-defined]
api_deps._app_settings = None  # type: ignore[attr-defined]
api_deps._conversations = None  # type: ignore[attr-defined]

# Build settings from env vars (all prefixed with E2E_).
from mechanic.config import Settings  # noqa: E402


def _env(key: str, default: str) -> str:
    """Return the value of an E2E_* environment variable."""
    return os.environ.get(f"E2E_{key}", default)


_e2e_settings = Settings(
    _env_file=None,
    ml_api_url=_env("ML_URL", "http://127.0.0.1:8001"),
    toir_api_url=_env("TOIR_URL", "http://127.0.0.1:8002"),
    rag_api_url=_env("RAG_URL", "http://127.0.0.1:8003"),
    app_data_dir=Path(_env("APP_DATA", str(Path("data")))),
    static_dir=Path(_env("STATIC", str(Path("static/dist")))),
    db_file=Path(_env("DB_FILE", "")) if _env("DB_FILE", "") else None,
)

# Initialise the hub and app-settings singletons.
# The lifespan is NOT run for a mounted sub-app, so we do it here.
from mechanic.api.deps import init_app_settings, init_hub  # noqa: E402

init_hub(_e2e_settings)
init_app_settings(_e2e_settings)

# Bootstrap admin (no-op if the admin was already seeded by conftest).
from mechanic.api.deps import get_hub  # noqa: E402

get_hub().auth.bootstrap_admin()

# Build the real app and mount it at /mech.
from mechanic.main import create_app  # noqa: E402

api = create_app(_e2e_settings)

app = FastAPI(title="Digital Mechanic E2E subpath wrapper")
app.mount("/mech", api)


@app.get("/mech")
def _redirect_root() -> RedirectResponse:
    """Redirect /mech to /mech/ (matches nginx location = /mech redirect)."""
    return RedirectResponse(url="/mech/", status_code=307)
