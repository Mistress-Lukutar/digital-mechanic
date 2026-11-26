"""
File:   conftest.py
Brief:  Pytest fixtures for the E2E test stand (mock services, API server, Playwright).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Session-scoped fixtures:
- ``stand``: allocates ports, seeds auth DB, spawns mock ML/TOiR and API servers,
  polls for readiness, yields a dataclass with connection info, and tears down
  all processes on fixture teardown.
- ``pw``: Playwright entry point.
- ``browser``: resolves a system browser channel (msedge > chrome > bundled).
- ``page``: creates a fresh page with ErrorMonitor attached; asserts clean
  teardown after each test function.

Function-scoped fixtures replace pytest-playwright's built-in ``page`` fixture.
"""

from __future__ import annotations

import dataclasses
import gc
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, sync_playwright

from e2e.error_monitor import ErrorMonitor
from mechanic.services.auth import AuthService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
PY: str = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")

PAGE_TIMEOUT_MS: int = 15000
HEALTH_DEADLINE_S: float = 30.0

ADMIN_USER: str = "admin"
ADMIN_PASSWORD: str = "e2e-admin-pass-123"
USER_USER: str = "e2euser"
USER_PASSWORD: str = "e2e-user-pass-123"


@dataclasses.dataclass(frozen=True)
class StandInfo:
    """Connection info for the running test stand."""

    base_url: str
    admin_user: str
    admin_password: str
    user_user: str
    user_password: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Reserve an ephemeral free TCP port and return it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop(proc: subprocess.Popen[Any]) -> None:
    """Terminate a spawned server process, escalating to kill."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _wait_health(base_url: str, run_dir: Path) -> None:
    """Poll ``GET {base_url}health`` until 200, else raise with log tails.

    Args:
        base_url: Stand base URL ending with ``/mech/``.
        run_dir: Directory holding the server log files.

    Raises:
        RuntimeError: When the API does not become healthy in time.
    """
    health_url = base_url + "health"
    deadline = time.monotonic() + HEALTH_DEADLINE_S
    last_err = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError) as exc:
            last_err = str(exc)
        time.sleep(0.3)

    tails: list[str] = []
    for name in ("mock_ml.log", "mock_toir.log", "api.log"):
        try:
            text = (run_dir / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = "<unreadable>"
        tails.append(f"--- {name} (tail) ---\n{text[-2000:]}")
    raise RuntimeError(
        f"E2E stand did not become healthy in {HEALTH_DEADLINE_S}s "
        f"(last error: {last_err}).\n" + "\n".join(tails)
    )


# ---------------------------------------------------------------------------
# Session fixture: Playwright entry point
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pw() -> Iterator[Any]:  # playwright.sync_api.Playwright
    """Start the Playwright session."""
    with sync_playwright() as p:
        yield p


# ---------------------------------------------------------------------------
# Session fixture: browser channel resolution
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def browser(pw: Any) -> Iterator[Any]:  # playwright.sync_api.Browser
    """Resolve a system browser channel and return a launched browser.

    Tries the channel from ``DM_E2E_CHANNEL`` env var, then falls back to
    ``msedge``, ``chrome``, and finally bundled chromium (no channel).
    Raises RuntimeError if none can be launched.
    """
    channel_order: list[str | None] = []
    dm_channel = os.environ.get("DM_E2E_CHANNEL")
    if dm_channel:
        channel_order.append(dm_channel)
    else:
        channel_order.extend(["msedge", "chrome"])

    last_exc: Exception | None = None
    launched: Any | None = None
    for ch in channel_order:
        kwargs: dict[str, Any] = {"headless": True}
        if ch is not None:
            kwargs["channel"] = ch
        try:
            probe = pw.chromium.launch(**kwargs)  # type: ignore[arg-type]
            probe.close()
            launched = pw.chromium.launch(**kwargs)  # type: ignore[arg-type]
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc

    if launched is None:
        # Last resort: bundled chromium (no channel).
        try:
            launched = pw.chromium.launch(headless=True)
        except Exception as exc2:  # noqa: BLE001
            raise RuntimeError(
                "Could not launch any browser. Last error: "
                f"{last_exc} (bundled: {exc2})"
            ) from exc2
    yield launched
    launched.close()


# ---------------------------------------------------------------------------
# Session fixture: the test stand
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def stand(tmp_path_factory: pytest.TempPathFactory) -> Iterator[StandInfo]:
    """Boot the whole stand: mocks + API (under /mech) and yield its info.

    The auth DB is seeded directly (admin + regular user with known
    passwords) before the server process starts, so no bootstrap password
    parsing is needed. Ports are picked dynamically so the suite never
    clashes with a live stand on 8001/8002/8011.
    """
    run_dir = tmp_path_factory.mktemp("e2e-stand")
    db_path = run_dir / "e2e.db"

    # Seed users first; drop the handle so the server owns the file after.
    auth = AuthService(db_path)
    auth.create_user(ADMIN_USER, ADMIN_PASSWORD, "admin")
    auth.create_user(USER_USER, USER_PASSWORD, "user")
    del auth
    gc.collect()

    ml_port, toir_port, api_port = _free_port(), _free_port(), _free_port()

    def _spawn(
        args: list[str], log_name: str, extra_env: dict[str, str]
    ) -> subprocess.Popen[Any]:
        """Spawn a server subprocess with stdout/stderr merged into a log."""
        log = (run_dir / log_name).open("w", encoding="utf-8", errors="replace")
        env = os.environ.copy()
        env.update(extra_env)
        return subprocess.Popen(
            args, cwd=REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
        )

    mock_env = {"MOCK_DATA_PATH": str(REPO_ROOT / "data" / "vehicles.json")}
    procs = [
        _spawn(
            [PY, "-m", "uvicorn", "mock_ml.app:app",
             "--port", str(ml_port), "--app-dir", "vendor"],
            "mock_ml.log", mock_env,
        ),
        _spawn(
            [PY, "-m", "uvicorn", "mock_toir.app:app",
             "--port", str(toir_port), "--app-dir", "vendor"],
            "mock_toir.log", mock_env,
        ),
        _spawn(
            [PY, "-m", "uvicorn", "e2e._subpath_app:app",
             "--port", str(api_port), "--app-dir", "."],
            "api.log",
            {
                "E2E_ML_URL": f"http://127.0.0.1:{ml_port}",
                "E2E_TOIR_URL": f"http://127.0.0.1:{toir_port}",
                # Closed port on purpose: RAG must hit its honest fallback.
                "E2E_RAG_URL": "http://127.0.0.1:1",
                "E2E_DB_FILE": str(db_path),
                "E2E_APP_DATA": str(REPO_ROOT / "data"),
                "E2E_STATIC": str(REPO_ROOT / "static" / "dist"),
            },
        ),
    ]

    try:
        base_url = f"http://127.0.0.1:{api_port}/mech/"
        _wait_health(base_url, run_dir)
        yield StandInfo(
            base_url=base_url,
            admin_user=ADMIN_USER,
            admin_password=ADMIN_PASSWORD,
            user_user=USER_USER,
            user_password=USER_PASSWORD,
        )
    finally:
        for proc in procs:
            _stop(proc)


# ---------------------------------------------------------------------------
# Function fixture: monitored page
# ---------------------------------------------------------------------------


@pytest.fixture()
def page(browser: Any) -> Iterator[Page]:
    """Fresh browser page per test with an ``ErrorMonitor`` attached.

    At teardown the monitor asserts the page produced no unexpected JS /
    console / HTTP errors, then the context is closed regardless.
    """
    context = browser.new_context()
    pg = context.new_page()
    pg.set_default_timeout(PAGE_TIMEOUT_MS)
    monitor = ErrorMonitor()
    monitor.attach(pg)
    try:
        yield pg
        monitor.assert_clean()
    finally:
        context.close()
