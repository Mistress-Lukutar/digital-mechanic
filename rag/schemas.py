'''
File:   schemas.py
Brief:  Request models for the RAG service endpoints.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

Response shapes come from shared/models.py (SearchResponse, PageContent) —
imported, not redefined. Only the request side is defined here.
'''

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    '''POST /search request body (contract fields plus two optional ones).'''

    query: str = Field(min_length=1, max_length=500)
    engine_model: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    # Optional extensions agreed in roadmap v2 §1.1; the backend's current
    # client does not send them, the service works fine without.
    fault_code: str | None = Field(
        default=None, pattern=r"^F(0[1-9]|1[0-4])$"
    )
    doc_id: str | None = None

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        '''Reject whitespace-only queries.'''
        if not value.strip():
            raise ValueError("query must not be blank")
        return value


__all__: list[str] = ["SearchRequest"]
