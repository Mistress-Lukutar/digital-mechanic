'''
File:   toir_client.py
Brief:  Async client for the Mock TOiR / ticket service (POST /tickets).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations

import httpx
from shared.models import TicketPayload, TicketResult

from mechanic.errors import MockApiError


class ToirClient:
    """HTTP client for the Mock TOiR ticket endpoint."""

    def __init__(
        self,
        base_url: str,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise the client.

        Args:
            base_url: Root URL of the Mock TOiR service.
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

    async def submit_ticket(self, payload: TicketPayload) -> TicketResult:
        """Call POST /tickets and return a parsed ``TicketResult``.

        Args:
            payload: The ticket payload to submit.

        Returns:
            A validated ``TicketResult`` model instance.

        Raises:
            MockApiError: On non-201 responses or connection errors.
        """
        url = f"{self._base_url}/tickets"

        try:
            response = await self._http.post(url, json=payload.model_dump())
        except httpx.RequestError as exc:
            raise MockApiError(
                "mock-toir", 503, f"mock TOiR service unreachable: {exc}"
            ) from exc

        if response.status_code == 201:
            return TicketResult.model_validate(response.json())

        # Non-201 → extract detail or truncate body.
        try:
            detail = response.json().get("detail", "")
        except Exception:  # noqa: BLE001
            detail = ""

        if not detail:
            text = response.text[:300]
            detail = text if len(text) < 300 else text + "..."

        raise MockApiError("mock-toir", response.status_code, detail)
