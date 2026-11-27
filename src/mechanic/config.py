'''
File:   config.py
Brief:  Application settings loaded from environment / .env (spec F6).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Mock service URLs, the LLM endpoint and data locations come from environment
variables (optionally a .env file in the working directory) so that real
services can be substituted without code changes.
'''

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    '''Application configuration (environment / .env).'''

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Mock service URLs (spec F6) ---
    ml_api_url: str = "http://127.0.0.1:8001"
    toir_api_url: str = "http://127.0.0.1:8002"
    rag_api_url: str = "http://127.0.0.1:8003"

    # --- LLM endpoint (bootstrap default; the admin can change it in the UI) ---
    llm_protocol: str = "openai_compatible"
    llm_base_url: str = "http://127.0.0.1:8010/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.3
    llm_max_output_tokens: int | None = None

    # --- Application ---
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_data_dir: Path = Path("data")
    manuals_dir: Path = Path("data/manuals")

    # Confidence floor for tickets: below it the agent must not create a
    # ticket and recommends re-recording (customer-accepted 0.50 threshold).
    confidence_ticket_floor: float = 0.50

    # Built frontend served by the API process when the directory exists
    # (single-process deployment; dev without a build is unaffected).
    static_dir: Path = Path("static/dist")
    # Explicit DB file override (tests point it at a tmp dir); when unset the
    # DB lives inside app_data_dir.
    db_file: Path | None = None

    # Initial admin password at first startup. When empty, a random
    # password is generated and logged once (bootstrap); set it via env
    # ADMIN_INITIAL_PASSWORD to avoid logging any secret.
    admin_initial_password: str = ""

    @property
    def vehicles_path(self) -> Path:
        '''Path of the issued fleet file.'''
        return self.app_data_dir / "vehicles.json"

    @property
    def fault_types_path(self) -> Path:
        '''Path of the fault type catalog.'''
        return self.app_data_dir / "fault_types.json"

    @property
    def mock_chunks_path(self) -> Path:
        '''Optional dev-only chunks file consumed by the mock RAG search.'''
        return self.app_data_dir / "rag" / "mock_chunks.jsonl"

    def resolve_db_path(self) -> Path:
        '''Path of the application SQLite database (auth, ticket log, usage).'''
        if self.db_file is not None:
            return self.db_file
        return self.app_data_dir / "app.db"


@lru_cache
def get_settings() -> Settings:
    '''Return the cached process-wide settings instance.'''
    return Settings()
