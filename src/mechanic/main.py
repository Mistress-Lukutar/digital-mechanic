'''
File:   main.py
Brief:  FastAPI application entry point with lifespan and bootstrap.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Creates the ``FastAPI`` app, wires all routers through a lifespan context
manager that initialises the service hub and app-settings store, prints
the bootstrap admin password at startup (when applicable), and exposes
a ``run()`` function for ``uvicorn`` via the console script entry point.
'''

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mechanic.api.admin_api import router as admin_router
from mechanic.api.auth_api import router as auth_router
from mechanic.api.chat_api import router as chat_router
from mechanic.api.deps import get_hub, init_app_settings, init_hub
from mechanic.api.documents_api import router as documents_router
from mechanic.api.tickets_api import router as tickets_router
from mechanic.api.vehicles_api import router as vehicles_router
from mechanic.config import get_settings
from mechanic.errors import MechanicError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> object:  # type: ignore[no-untyped-def]
    """Application lifespan: initialise hub and app-settings on startup.

    On shutdown nothing to close because all clients are process-long.
    """
    settings = get_settings()
    init_hub(settings)
    init_app_settings(settings)
    password = get_hub().auth.bootstrap_admin()
    if password is not None:
        logger.warning(
            "Bootstrap admin created: username='admin' "
            "password='%s' - change it after first login",
            password,
        )
    yield


def _get_hub() -> object:  # ServiceHub
    """Return the hub singleton (lazy import guard)."""
    from mechanic.api.deps import get_hub as _gh

    return _gh()


def create_app() -> FastAPI:
    """Construct and configure the ``FastAPI`` application.

    Returns:
        Configured :class:`FastAPI` instance ready for serving.
    """
    app = FastAPI(
        title="Digital Mechanic API",
        lifespan=lifespan,
    )

    # CORS middleware for development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler for MechanicError.
    @app.exception_handler(MechanicError)
    async def mechanic_error_handler(
        request: object, exc: Exception  # type: ignore[no-untyped-def]
    ) -> JSONResponse:
        """Handle :class:`~mechanic.errors.MechanicError` exceptions."""
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    # Register routers.
    app.include_router(auth_router)
    app.include_router(vehicles_router)
    app.include_router(chat_router)
    app.include_router(tickets_router)
    app.include_router(documents_router)
    app.include_router(admin_router)

    return app


def run() -> None:
    """Start the application server via uvicorn."""
    settings = get_settings()
    import uvicorn

    uvicorn.run(
        "mechanic.main:app",
        host=settings.app_host,
        port=settings.app_port,
    )


# Module-level app instance for uvicorn target ``mechanic.main:app``.
app = create_app()
