'''
File:   test_app_settings.py
Brief:  Unit tests for app_settings module.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Tests effective_llm_config merge logic, set/get/delete round-trips and
missing-key handling for the :class:`~mechanic.services.app_settings.AppSettings`
store.
'''

from __future__ import annotations

import tempfile
from pathlib import Path

from mechanic.config import Settings
from mechanic.services.app_settings import (
    AppSettings,
    LlmConfig,
    effective_llm_config,
)


def _make_db(tmp_path: Path) -> Path:
    """Return a temp db path inside *tmp_path*."""
    return tmp_path / "app.db"


def test_effective_merge_env_defaults() -> None:
    """env Settings override + stored dict merge produces correct LlmConfig."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "app.db"
        db = AppSettings(db_path)

        # Store partial overrides.
        db.set("llm", {"api_key": "dbkey", "model": "m"})

        settings = Settings(
            _env_file=None,
            llm_base_url="http://env:1/v1",
            llm_api_key="envkey",
        )

        cfg = effective_llm_config(settings, db)

        assert isinstance(cfg, LlmConfig)
        # base_url comes from env (not overridden in store).
        assert cfg.base_url == "http://env:1/v1"
        # api_key is overridden by stored value.
        assert cfg.api_key == "dbkey"
        # model is set from store.
        assert cfg.model == "m"
        # temperature stays at env default (0.3).
        assert cfg.temperature == 0.3

        db.close()


def test_set_get_delete_roundtrip() -> None:
    """Store a dict, retrieve it, then delete and verify None."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "app.db"
        db = AppSettings(db_path)

        payload = {"key1": "value1", "key2": 42}
        db.set("test_key", payload)

        result = db.get("test_key")
        assert result == payload

        db.delete("test_key")
        assert db.get("test_key") is None

        db.close()


def test_get_missing_key_returns_none() -> None:
    """Reading a non-existent key yields None."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "app.db"
        db = AppSettings(db_path)

        assert db.get("nonexistent") is None

        db.close()


def test_effective_no_stored_returns_env_defaults() -> None:
    """When nothing is stored, effective config equals env defaults."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "app.db"
        db = AppSettings(db_path)

        settings = Settings(
            _env_file=None,
            llm_protocol="anthropic",
            llm_base_url="http://custom:9000/v1",
            llm_api_key="secret123",
            llm_model="claude-sonnet",
            llm_temperature=0.7,
            llm_max_output_tokens=4096,
        )

        cfg = effective_llm_config(settings, db)

        assert cfg.protocol == "anthropic"
        assert cfg.base_url == "http://custom:9000/v1"
        assert cfg.api_key == "secret123"
        assert cfg.model == "claude-sonnet"
        assert cfg.temperature == 0.7
        assert cfg.max_output_tokens == 4096

        db.close()
