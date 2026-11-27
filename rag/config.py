'''
File:   config.py
Brief:  RAG module settings loaded from environment / .env.
Author: Demetrius242
Date:   2026-11-26
Version: v0.1.0

All knobs come from environment variables (optionally a .env in the working
directory) so the service can be reconfigured without code changes.
``MANUALS_DIR`` is shared with the backend (participant A reads the same
directory to serve PDF files); the rest are ``RAG_``-prefixed and owned by B.
'''

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RagSettings(BaseSettings):
    '''RAG module configuration (environment / .env).'''

    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Shared with the backend: where manifest.json and the PDF files live.
    # MANUALS_DIR is the backend's variable (src/mechanic/config.py).
    manuals_dir: Path = Field(
        default=Path("data/manuals"),
        validation_alias=AliasChoices("MANUALS_DIR", "RAG_MANUALS_DIR"),
    )
    # Built artifacts (gitignored): pages, chunks, index versions, caches.
    data_dir: Path = Path("data/rag")
    # External eval question sets (RAG_EVAL_DIR); not committed because
    # golden.jsonl quotes the manuals.
    eval_dir: Path = Path("data/eval")

    # "none" disables the dense part; the service then runs on BM25 only.
    embed_model: str = "BAAI/bge-m3"
    device: str = "auto"  # auto | cpu | cuda

    # tier thresholds over the comparable score (cosine or normalized BM25).
    tier_high: float = 0.70
    tier_med: float = 0.55

    # Chunks must survive the backend's per-hit cut of 800 chars
    # (src/mechanic/agent/tools_impl/manuals.py) with the fact intact.
    chunk_max_chars: int = 700
    # At most this many chunks from the same PDF page enter one response.
    max_per_page: int = 2
    # Pin a specific index version (e.g. "v003"); latest is used when None.
    index_version: str | None = None


@lru_cache
def get_settings() -> RagSettings:
    '''Return the cached process-wide settings instance.'''
    return RagSettings()


__all__: list[str] = ["RagSettings", "get_settings"]
