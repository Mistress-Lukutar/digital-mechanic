'''
File:   app_settings.py
Brief:  Application settings backed by SQLite; effective LLM config merger.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Provides a minimal key-value store in SQLite for persisting application
settings (currently only the LLM endpoint configuration). The module also
exposes ``effective_llm_config`` which merges environment-backed defaults
with stored values so the admin can override provider settings from the UI.
'''

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from pydantic import BaseModel

from mechanic.config import Settings


class LlmConfig(BaseModel):
    '''LLM endpoint configuration.

    Attributes:
        protocol: Provider protocol identifier (e.g. "openai_compatible").
        base_url: API base URL for the provider.
        api_key: Bearer token for API authentication.
        model: Model identifier string.
        temperature: Sampling temperature (0-1).
        max_output_tokens: Optional output token cap.
    '''

    protocol: str = "openai_compatible"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.3
    max_output_tokens: int | None = None


class EconomyPrices(BaseModel):
    '''Token prices for the economics calculator.

    Attributes:
        input_price: Price per 1 000 000 input tokens.
        output_price: Price per 1 000 000 output tokens.
        currency: "USD" or "RUB".
        usd_rate: Central-bank RUB/USD rate used when currency == "USD".
        model_label: Human-readable model/pricing source label.
        indexation_cost: One-off manual-indexing cost in RUB (separate line).
    '''

    input_price: float = 0.22
    output_price: float = 0.88
    currency: str = "USD"
    usd_rate: float = 82.313
    model_label: str = "Qwen3-30B-A3B (Alibaba Model Studio)"
    indexation_cost: float = 0.0


class AppSettings:
    '''Key-value settings store backed by SQLite (WAL mode).

    All values are serialised as JSON strings. The table schema is:
        app_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)

    Args:
        db_path: Filesystem path for the SQLite database file.
            Parent directories are created automatically.
    '''

    def __init__(self, db_path: Path) -> None:
        """Initialise the settings database.

        Creates parent directories, opens a connection with WAL journal mode,
        and creates the ``app_settings`` table if it does not exist.

        Args:
            db_path: Destination path for the SQLite database file.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_table()

    def _init_table(self) -> None:
        """Create the ``app_settings`` table if missing."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key        TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, key: str) -> dict | None:
        """Return the stored settings dict for *key*, or ``None``.

        Args:
            key: Setting key to look up.

        Returns:
            Parsed JSON dict, or ``None`` if the key does not exist.
        """
        cursor = self._conn.execute(
            "SELECT value_json FROM app_settings WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["value_json"])

    def set(self, key: str, value: dict) -> None:
        """Store *value* as JSON under *key*.

        Args:
            key: Setting key to store under.
            value: Dict to serialise and persist.
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO app_settings (key, value_json)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json
                """,
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        """Delete the setting identified by *key*.

        Args:
            key: Setting key to remove.
        """
        with self._lock:
            self._conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
            self._conn.commit()

    def get_economy_prices(self) -> EconomyPrices:
        """Return stored :class:`EconomyPrices`, or a default instance.

        When the key is absent or the stored JSON cannot be parsed,
        a default ``EconomyPrices`` is returned so callers never fail.

        Returns:
            :class:`EconomyPrices` instance.
        """
        try:
            data = self.get("economy_prices")
            if data is None:
                return EconomyPrices()
            return EconomyPrices(**data)
        except (json.JSONDecodeError, ValueError, TypeError):
            return EconomyPrices()

    def save_economy_prices(self, prices: EconomyPrices) -> None:
        """Persist *prices* to the settings store.

        Args:
            prices: :class:`EconomyPrices` instance to save.
        """
        self.set("economy_prices", prices.model_dump())

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def effective_llm_config(settings: Settings, db: AppSettings) -> LlmConfig:
    """Merge environment defaults with stored values into an ``LlmConfig``.

    Starts from the ``Settings`` instance (env-backed), then overlays any
    keys present in the stored dict under key ``"llm"`` so that UI-set
    values take precedence over environment defaults.

    Args:
        settings: Process-wide :class:`~mechanic.config.Settings` instance.
        db: :class:`AppSettings` instance providing persisted overrides.

    Returns:
        A fully-resolved :class:`LlmConfig`.
    """
    base = LlmConfig(
        protocol=settings.llm_protocol,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
    )

    stored = db.get("llm")
    if stored is None:
        return base

    # Overlay any present keys from the stored dict.
    data = base.model_dump()
    for k, v in stored.items():
        if k in data and v is not None:
            data[k] = v

    return LlmConfig(**data)
