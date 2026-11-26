'''
File:   errors.py
Brief:  Package exception hierarchy rooted at MechanicError.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
'''

from __future__ import annotations


class MechanicError(Exception):
    '''Base exception for all digital-mechanic package errors.'''


class FleetError(MechanicError):
    '''Raised when a vehicle or session is not found in the fleet data.'''


class MockApiError(MechanicError):
    '''Mock service (ML / TOiR / RAG) returned an HTTP error.

    Attributes:
        status_code: HTTP status returned by the service.
        detail: Human-readable detail from the service response, if any.
    '''

    def __init__(self, service: str, status_code: int, detail: str):
        self.service = service
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{service} error {status_code}: {detail}")


class RagUnavailableError(MechanicError):
    '''Raised when the RAG service cannot be reached or returns no page.

    The agent must treat this as "no manual data available", not invent one.
    '''
