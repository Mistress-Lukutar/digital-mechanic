'''
File:   ml_client.py
Brief:  Async client for the Mock ML / diagnostics service (POST /diagnose).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import httpx
from shared.models import DiagnosticResult

from mechanic.errors import MockApiError


class MlClient:
    """HTTP client for the Mock ML diagnostic endpoint."""

    def __init__(
        self,
        base_url: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            base_url: Root URL of the Mock ML service (e.g. ``http://127.0.0.1:8001``).
            http: Optional pre-existing ``httpx.AsyncClient``.  When *None* a new
                client is created with standard timeouts and owned by this instance.
        """
        self._base_url = base_url.rstrip("/")
        if http is not None:
            self._http = http
            self._owned = False
        else:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
            )
            self._owned = True

    async def aclose(self) -> None:
        """Close the HTTP client *only* if it was self-owned."""
        if self._owned:
            await self._http.aclose()

    async def diagnose(
        self, vehicle_id: str, session_id: str
    ) -> DiagnosticResult:
        """Call POST /diagnose and return a parsed ``DiagnosticResult``.

        Args:
            vehicle_id: Vehicle licence plate.
            session_id: Session identifier to diagnose.

        Returns:
            A validated ``DiagnosticResult`` model instance.

        Raises:
            MockApiError: On non-200 responses or connection errors.
        """
        url = f"{self._base_url}/diagnose"
        payload = {"vehicle_id": vehicle_id, "session_id": session_id}

        try:
            response = await self._http.post(url, json=payload)
        except httpx.RequestError as exc:
            raise MockApiError(
                "mock-ml", 503, f"mock ML service unreachable: {exc}"
            ) from exc

        if response.status_code == 200:
            return DiagnosticResult.model_validate(response.json())

        # Non-200 → extract detail or truncate body.
        try:
            detail = response.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detail = ""

        if not detail:
            text = response.text[:300]
            detail = text if len(text) < 300 else text + "..."

        raise MockApiError("mock-ml", response.status_code, detail)
