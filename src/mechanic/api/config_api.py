'''
File:   config_api.py
Brief:  Configuration status endpoint that probes RAG, documents manifest, and LLM.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.0

Provides the ``/api/config-status`` router with a single GET endpoint that
returns structured diagnostics about the backend configuration (RAG service
availability, document manifest health, LLM endpoint reachability). Results
are cached for 30 seconds to avoid hammering external services on every call.
'''

from __future__ import annotations

import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from mechanic.api.deps import get_hub
from mechanic.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["config"])


# ---------------------------------------------------------------------------
# Auth dependency (mirrors chat_api._auth_user).
# ---------------------------------------------------------------------------


async def _auth_user(request: Request) -> object:  # TokenUser
    """Resolve bearer token to :class:`TokenUser`."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    token = auth_header[7:]
    user = get_hub().auth.resolve_token(token)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="требуется авторизация",
        )
    return user


class ConfigCheck(BaseModel):
    """A single configuration check result.

    Attributes:
        check: Machine-readable identifier for the check (e.g. ``rag_service``).
        ok: Whether the check passed.
        detail: Human-readable diagnostic message (Russian).
        hint: Actionable hint on failure (Russian).
    """

    check: str
    ok: bool
    detail: str
    hint: str


class ConfigStatus(BaseModel):
    """Aggregated configuration status response.

    Attributes:
        overall: ``True`` only when all checks pass.
        checks: List of individual check results.
    """

    overall: bool
    checks: list[ConfigCheck]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_cache: tuple[float, ConfigStatus] | None = None
_CACHE_TTL_SECONDS: float = 30.0

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


async def _check_rag_service() -> ConfigCheck:
    """Probe the RAG service health endpoint.

    Returns:
        A :class:`ConfigCheck` describing the outcome.
    """
    settings = get_settings()
    url = f"{settings.rag_api_url.rstrip('/')}/health"

    try:
        timeout = httpx.Timeout(connect=3.0, read=3.0, write=3.0, pool=3.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return ConfigCheck(
                    check="rag_service",
                    ok=True,
                    detail="RAG-сервис отвечает",
                    hint="",
                )
    except httpx.RequestError as exc:
        return ConfigCheck(
            check="rag_service",
            ok=False,
            detail=f"RAG-сервис недоступен: {exc}",
            hint="Запустите rag-сервис (порт из RAG_API_URL, по умолчанию 8003) — "  # noqa: E501
                 "scripts/start или README раздел RAG",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG health check failed: %s", exc)
        return ConfigCheck(
            check="rag_service",
            ok=False,
            detail=f"RAG-сервис недоступен: {exc}",
            hint="Запустите rag-сервис (порт из RAG_API_URL, по умолчанию 8003) — "  # noqa: E501
                 "scripts/start или README раздел RAG",
        )

    return ConfigCheck(
        check="rag_service",
        ok=False,
        detail=f"RAG-сервис вернул HTTP {response.status_code}",
        hint="Запустите rag-сервис (порт из RAG_API_URL, по умолчанию 8003) — "  # noqa: E501
             "scripts/start или README раздел RAG",
    )


async def _check_documents() -> ConfigCheck:
    """Verify the documents manifest is present and non-empty.

    Returns:
        A :class:`ConfigCheck` describing the outcome.
    """
    hub = get_hub()
    try:
        docs = list(hub.manifest._docs.values())
        count = len(docs)
        if count > 0:
            return ConfigCheck(
                check="documents",
                ok=True,
                detail=f"{count} документов в индексе",
                hint="",
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Documents manifest check failed: %s", exc)

    return ConfigCheck(
        check="documents",
        ok=False,
        detail="Манифест документов пуст или отсутствует",
        hint="Выполните python -m rag.setup --from <папка с PDF> и "  # noqa: E501
             "перезапустите rag-сервис",
    )


async def _check_llm_endpoint() -> ConfigCheck:
    """Probe the LLM endpoint /models or report it is unconfigured.

    Returns:
        A :class:`ConfigCheck` describing the outcome.
    """
    settings = get_settings()
    base_url = settings.llm_base_url.strip()

    if not base_url:
        return ConfigCheck(
            check="llm_endpoint",
            ok=False,
            detail="LLM endpoint не настроен",
            hint="Задайте LLM_BASE_URL в .env",
        )

    url = f"{base_url.rstrip('/')}/models"
    headers: dict[str, str] = {}
    api_key = settings.llm_api_key.strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        timeout = httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                return ConfigCheck(
                    check="llm_endpoint",
                    ok=True,
                    detail="LLM endpoint отвечает",
                    hint="",
                )
    except httpx.RequestError as exc:
        return ConfigCheck(
            check="llm_endpoint",
            ok=False,
            detail=f"LLM endpoint недоступен: {exc}",
            hint="Проверьте LLM_BASE_URL / ключ в .env; локальный "  # noqa: E501
                 "сервер должен быть запущен",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM endpoint check failed: %s", exc)
        return ConfigCheck(
            check="llm_endpoint",
            ok=False,
            detail=f"LLM endpoint недоступен: {exc}",
            hint="Проверьте LLM_BASE_URL / ключ в .env; локальный "  # noqa: E501
                 "сервер должен быть запущен",
        )

    return ConfigCheck(
        check="llm_endpoint",
        ok=False,
        detail=f"LLM endpoint вернул HTTP {response.status_code}",
        hint="Проверьте LLM_BASE_URL / ключ в .env; локальный "  # noqa: E501
             "сервер должен быть запущен",
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/config-status")
async def config_status(user=Depends(_auth_user)) -> ConfigStatus:
    """Return aggregated configuration diagnostics.

    Results are cached for 30 seconds to avoid repeated external probes.
    Each check is wrapped in try/except so no exception escapes the endpoint.

    Args:
        user: Authenticated user from :func:`_auth_user`.

    Returns:
        A :class:`ConfigStatus` with ``overall`` and ``checks`` fields.
    """
    global _cache

    now = time.monotonic()
    if _cache is not None:
        cache_ts, cached = _cache
        if now - cache_ts < _CACHE_TTL_SECONDS:
            return cached

    checks: list[ConfigCheck] = []

    checks.append(await _check_rag_service())
    checks.append(await _check_documents())
    checks.append(await _check_llm_endpoint())

    overall = all(c.ok for c in checks)
    result = ConfigStatus(overall=overall, checks=checks)
    _cache = (now, result)
    return result


# ---------------------------------------------------------------------------
# Export the router after registration.
# ---------------------------------------------------------------------------

__all__: list[str] = ["router", "ConfigStatus", "ConfigCheck"]
