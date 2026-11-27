"""
File:   test_static_assets.py
Brief:  Regression tests for issue #12 — .mjs ES-module assets served with
        wrong Content-Type (text/plain instead of text/javascript), causing
        browsers to reject dynamic import() in pdf.js worker.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

Two tests:
- test_mjs_assets_served_as_javascript: verifies HTTP Content-Type for .mjs files.
- test_browser_can_import_worker_module: exercises dynamic import() in a real browser.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Test 1: .mjs assets served with correct JavaScript Content-Type
# ---------------------------------------------------------------------------


def test_mjs_assets_served_as_javascript(stand: Any) -> None:
    """Built .mjs assets must be served with a JavaScript MIME type."""
    assets_dir = REPO_ROOT / "static" / "dist" / "assets"
    mjs_files = sorted(p.name for p in assets_dir.glob("*.mjs"))

    assert mjs_files, (
        "No built .mjs assets in static/dist/assets; run npm run build"
    )

    base = stand.base_url  # e.g. http://127.0.0.1:XXXX/mech/
    for name in mjs_files:
        url = base + "assets/" + name
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            ct = resp.headers.get("Content-Type", "")
            media_type = (ct.split(";")[0].strip().lower())
            assert media_type in ("text/javascript", "application/javascript"), (
                f"Asset '{name}' at {url} served with Content-Type='{ct}' "
                f"(media type '{media_type}'); expected 'text/javascript' or "
                f"'application/javascript'"
            )

# ---------------------------------------------------------------------------
# Test 2: Browser can dynamically import the pdf.js worker module
# ---------------------------------------------------------------------------


def test_browser_can_import_worker_module(page: Any, stand: Any) -> None:
    """Each .mjs asset must be importable via dynamic import() in a browser.

    Reproduces issue #12: pdf.worker.min.mjs is served as text/plain, so the
    browser rejects it as an ES module and import() raises TypeError.
    """
    assets_dir = REPO_ROOT / "static" / "dist" / "assets"
    mjs_files = sorted(p.name for p in assets_dir.glob("*.mjs"))

    assert mjs_files, (
        "No built .mjs assets in static/dist/assets; run npm run build"
    )

    page.goto(stand.base_url)

    base = stand.base_url  # e.g. http://127.0.0.1:XXXX/mech/
    for name in mjs_files:
        url = base + "assets/" + name
        result = page.evaluate(
            "async (u) => { const m = await import(u); return typeof m; }", url
        )
        assert result == "object", (
            f"Dynamic import() of '{url}' returned '{result}', expected 'object'. "
            "The browser likely rejected the module due to wrong Content-Type."
        )
