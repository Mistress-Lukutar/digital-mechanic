'''
File:   models.py
Brief:  Shared contract models (specification v6 section 5 and team contracts).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Single source of truth for the data contracts crossing service boundaries:
the Mock ML response, the Mock TOiR ticket payload, the fleet file layout and
the RAG service contracts. Imported by the backend (src/mechanic) and by the
RAG module built by participant B. Keep this module dependency-free (pydantic
only) — it must stay importable from any service in the same environment.
'''

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ======================================================================
# Mock ML / diagnostics contract (specification v6 section 5, POST /diagnose).
# ======================================================================

DiagnosticStatus = Literal["normal", "anomaly", "check_failed"]
SignalQuality = Literal["good", "warning", "bad"]


class DiagnosticResult(BaseModel):
    '''Result of one acoustic check as returned by Mock ML POST /diagnose.

    ``checked_at`` is absent in the /diagnose response but present in
    vehicles.json session records; optional so both sources parse.
    '''

    vehicle_id: str = Field(min_length=1, examples=["M333YK47"])
    session_id: str = Field(min_length=1, examples=["S-0005"])
    status: DiagnosticStatus
    anomaly_type: str | None = Field(
        default=None,
        pattern=r"^F(0[1-9]|1[0-4])$",
        description="Fault type code F01…F14, null when normal/check_failed",
    )
    anomaly_title: str | None = None
    anomaly_score: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    signal_quality: SignalQuality
    description: str
    model_version: str
    checked_at: str | None = Field(
        default=None,
        description="ISO 8601 check time; only in vehicles.json records",
    )


class SessionCheck(DiagnosticResult):
    '''One session record from vehicles.json (a DiagnosticResult + timestamp).'''


class FaultType(BaseModel):
    '''Fault type catalog entry (fault_types.json).'''

    code: str = Field(pattern=r"^F(0[1-9]|1[0-4])$")
    title: str


# ======================================================================
# Fleet file contract (vehicles.json).
# ======================================================================


class Vehicle(BaseModel):
    '''Vehicle card with its check history, as stored in vehicles.json.'''

    vehicle_id: str = Field(min_length=1, description="License plate, Latin")
    garage_no: str
    make: str
    model: str | None = None
    vehicle_type: str
    engine_model: str
    fuel: str
    sessions: list[SessionCheck] = Field(default_factory=list)


class FleetFile(BaseModel):
    '''Root object of the issued vehicles.json file.'''

    schema_version: int = 1
    event: str | None = None
    synthetic: bool | None = None
    model_version: str | None = None
    vehicles: list[Vehicle] = Field(default_factory=list)


# ======================================================================
# Mock TOiR ticket contract (specification v6 section 5, POST /tickets).
# ======================================================================

Urgency = Literal["low", "medium", "high"]


class Reference(BaseModel):
    '''Citation of a manual page; pages are counted per the PDF, from 1.'''

    manual: str = Field(
        min_length=1,
        description="Document designation exactly as in specification v6 section 3",
    )
    pdf_page: int = Field(ge=1)


class TicketPayload(BaseModel):
    '''Defect inspection ticket sent to Mock TOiR POST /tickets.

    All fields are mandatory; ``operations`` and ``references`` must be
    non-empty, ``spare_parts`` may be empty.
    '''

    vehicle_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    anomaly_type: str = Field(pattern=r"^F(0[1-9]|1[0-4])$")
    conclusion: str = Field(min_length=1)
    urgency: Urgency
    operations: list[str] = Field(min_length=1)
    spare_parts: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(min_length=1)


class TicketResult(BaseModel):
    '''Mock TOiR response confirming ticket creation.'''

    ticket_id: str = Field(examples=["TKT-0001"])
    status: Literal["created"] = "created"


class TicketRecord(BaseModel):
    '''Locally kept ticket log entry (B1 vehicle memory; the TOiR stub
    does not return ticket history).'''

    ticket_id: str
    created_at: datetime
    payload: TicketPayload


# ======================================================================
# RAG service contract (team contract 1 with participant B).
# ======================================================================

SearchTier = Literal["high", "med", "low"]


class SearchHit(BaseModel):
    '''One retrieved manual fragment with its citation coordinates.'''

    doc_id: str = Field(examples=["236.01.01 РК"])
    doc_title: str
    page_pdf: int = Field(ge=1, description="PDF page number, 1-based")
    section: str | None = None
    text: str
    score: float | None = None
    tier: SearchTier | None = None


class SearchResponse(BaseModel):
    '''RAG POST /search response.

    ``no_instruction=True`` with empty results is the explicit signal that
    the manuals for this engine contain no matching instructions.
    '''

    results: list[SearchHit] = Field(default_factory=list)
    no_instruction: bool = False


class PageContent(BaseModel):
    '''RAG GET /document/{doc_id}/page/{page_pdf} response: page text plus
    the local PDF path for the document panel.'''

    doc_id: str
    doc_title: str | None = None
    page_pdf: int = Field(ge=1)
    text: str
    pdf_path: str | None = Field(
        default=None,
        description="Path of the PDF file on the server, when available",
    )
