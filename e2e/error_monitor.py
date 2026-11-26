'''
File:   error_monitor.py
Brief:  Monitors a Playwright page for JS errors, console errors, and HTTP failures.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Attaches listeners to a Playwright Page that collect:
- JavaScript exceptions (pageerror event)
- Console.error messages
- HTTP responses with status >= 400
- Failed requests

Provides an allowlist for expected 4xx semantics and an assert_clean() method
that raises AssertionError listing every unexpected item.
'''

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# Chrome echoes every non-2xx resource as a bare console error WITHOUT the
# URL ("Failed to load resource: the server responded with a status of 401").
# Those are duplicates of the response-event tracking below (which enforces
# the URL+status allowlist), so they are skipped entirely.
_RESOURCE_LOAD_RE = re.compile(
    r"Failed to load resource: .*status of \d+"
)


@dataclass(frozen=True)
class ErrorItem:
    """A single error captured from the page."""

    description: str

    def __str__(self) -> str:  # noqa: D105
        return self.description


# ---------------------------------------------------------------------------
# Allowlist patterns: (url_substring, status_code) tuples that are expected.
# ---------------------------------------------------------------------------

ALLOWLISTED_ITEMS: list[tuple[str, int]] = [
    # Auth: wrong-password UX path returns 401 on login.
    ("/api/auth/login", 401),
    # Auth: unauthenticated /me returns 401.
    ("/api/auth/me", 401),
]


class ErrorMonitor:
    """Collects errors from a Playwright page and asserts cleanliness."""

    def __init__(self) -> None:
        self._page_errors: list[ErrorItem] = []
        self._console_errors: list[ErrorItem] = []
        self._http_failures: list[ErrorItem] = []
        self._request_fails: list[ErrorItem] = []

    # ------------------------------------------------------------------
    # Attachment
    # ------------------------------------------------------------------

    def attach(self, page: Page) -> None:  # noqa: A003
        """Register Playwright error listeners on *page*."""

        page.on(
            "pageerror",
            lambda exc: self._page_errors.append(
                ErrorItem(f"JS exception: {exc}")
            ),
        )

        page.on(
            "console",
            lambda msg: (
                self._console_errors.append(
                    ErrorItem(f"Console error: {msg.text}")
                )
                if msg.type == "error"
                and not _RESOURCE_LOAD_RE.search(msg.text)
                else None
            ),
        )

        page.on(
            "response",
            lambda resp: (
                self._http_failures.append(
                    ErrorItem(f"HTTP {resp.status} GET {resp.url}")
                )
                if resp.status >= 400
                else None
            ),
        )

        page.on(
            "requestfailed",
            lambda req: self._request_fails.append(
                ErrorItem(
                    f"Request failed: {req.url} -> {req.failure.error_message}"
                )
                if req.failure
                else ErrorItem(f"Request failed: {req.url}")
            ),
        )

    # ------------------------------------------------------------------
    # Allowlist check
    # ------------------------------------------------------------------

    def _is_allowlisted(self, item: ErrorItem) -> bool:
        """Return True if *item* matches an allowlisted (url, status) pair."""
        for url_substring, expected_status in ALLOWLISTED_ITEMS:
            if str(expected_status) in str(item) and url_substring in str(item):
                return True
        return False

    # ------------------------------------------------------------------
    # Assertion
    # ------------------------------------------------------------------

    def assert_clean(self) -> None:
        """Raise ``AssertionError`` listing every unexpected error item."""
        unexpected: list[str] = []
        buckets = (
            self._page_errors,
            self._console_errors,
            self._http_failures,
            self._request_fails,
        )
        for bucket in buckets:
            unexpected.extend(
                str(item) for item in bucket if not self._is_allowlisted(item)
            )

        if unexpected:
            details = "\n".join(f"  - {line}" for line in unexpected)
            raise AssertionError(
                f"Error monitor detected {len(unexpected)} item(s):\n{details}"
            )
