'''
File:   test_static.py
Brief:  Integration tests for static frontend serving and /health.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Exercises the single-process deployment surface: the liveness probe, the
built-dist static files, the SPA fallback and the guard that keeps unknown
API paths from returning HTML. Uses ``httpx.AsyncClient`` with
``ASGITransport``; no service hub is needed because the static routes
touch no services.
'''

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from mechanic.config import Settings
from mechanic.main import create_app


@pytest.fixture()
def static_client(tmp_path: Path) -> httpx.AsyncClient:
    """App with an isolated built-dist directory inside *tmp_path*."""
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<html>spa-entry</html>', encoding='utf-8')
    (dist / 'favicon.svg').write_text('<svg/>', encoding='utf-8')
    (dist / 'assets' / 'app.js').write_text('console.log(1);', encoding='utf-8')

    settings = Settings(_env_file=None, static_dir=dist)
    app = create_app(settings)
    return httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url='http://testserver',
    )


async def test_health_probe(static_client: httpx.AsyncClient) -> None:
    """GET /health returns the liveness payload."""
    response = await static_client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


async def test_root_serves_index_html(static_client: httpx.AsyncClient) -> None:
    """GET / returns the SPA entry point as HTML."""
    response = await static_client.get('/')
    assert response.status_code == 200
    assert 'spa-entry' in response.text
    assert response.headers['content-type'].startswith('text/html')


async def test_favicon_served(static_client: httpx.AsyncClient) -> None:
    """Static files at the dist root are served."""
    response = await static_client.get('/favicon.svg')
    assert response.status_code == 200
    assert '<svg/>' in response.text


async def test_assets_mount_served(static_client: httpx.AsyncClient) -> None:
    """Bundled assets are served via the /assets mount."""
    response = await static_client.get('/assets/app.js')
    assert response.status_code == 200
    assert 'console.log(1);' in response.text


async def test_spa_fallback_returns_index(static_client: httpx.AsyncClient) -> None:
    """Unknown non-API paths fall back to the SPA entry point."""
    response = await static_client.get('/some/spa/route')
    assert response.status_code == 200
    assert 'spa-entry' in response.text
    assert response.headers['content-type'].startswith('text/html')


async def test_unknown_api_path_returns_404(static_client: httpx.AsyncClient) -> None:
    """Unknown /api paths return 404, never the SPA HTML."""
    response = await static_client.get('/api/does-not-exist')
    assert response.status_code == 404
    assert 'spa-entry' not in response.text


async def test_traversal_returns_no_repo_file(static_client: httpx.AsyncClient) -> None:
    """Encoded traversal must not leak files outside the dist directory.

    ``httpx`` normalizes plain dot segments, so the request uses percent
    encoded ones. The assertion checks a pyproject.toml marker instead of
    the status code because the client may collapse the path to a legal
    SPA route before sending.
    """
    response = await static_client.get('/%2e%2e/%2e%2e/pyproject.toml')
    assert '[build-system]' not in response.text
