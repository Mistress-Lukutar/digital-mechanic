"""
File:   test_prompt.py
Brief:  Tests for the language-aware system-prompt builder and ChatRequest model.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Verifies that build_system_prompt appends the correct language block for each
supported locale, falls back to Russian on unknown values, and that the
ChatRequest Pydantic model rejects invalid literals.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pytest

from mechanic.api.chat_api import ChatRequest

# ---------------------------------------------------------------------------
# Reuse the hub builder from test_agent_tools so no real services are needed.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT / "tests" / "unit"))
from test_agent_tools import _build_test_hub  # noqa: E402


def _prompt(hub: Any, vehicle_id: str = "M333YK47", **kwargs: object) -> str:
    """Call build_system_prompt with the given *hub* and keyword args.

    Args:
        hub: A :class:`~mechanic.services.hub.ServiceHub` instance.
        vehicle_id: Vehicle identifier (default ``M333YK47``).
        **kwargs: Extra keyword arguments forwarded to
            :func:`mechanic.agent.prompt.build_system_prompt`.

    Returns:
        The resulting system prompt string.
    """
    from mechanic.agent.prompt import build_system_prompt

    return build_system_prompt(hub, vehicle_id, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


class TestLanguageBlockRu:
    """Default / explicit Russian language produces the question-language rule."""

    def test_default_ru_contains_question_language_rule(
        self, monkeypatch: Any
    ) -> None:
        """Default (language="ru") → block with 'языку вопроса' and no 'казахский'."""
        hub = _build_test_hub()
        result = _prompt(hub)

        assert "## ЯЗЫК ОТВЕТА" in result
        ru_msg = "Отвечай на языке вопроса пользователя (по умолчанию — русский)."
        assert ru_msg in result
        assert "казахский" not in result


class TestLanguageBlockKk:
    """Kazakh language produces the explicit target-language block."""

    def test_kk_contains_target_language(self) -> None:
        """language='kk' → prompt contains 'казахский (қазақша)' rule."""
        hub = _build_test_hub()
        result = _prompt(hub, language="kk")

        assert "## ЯЗЫК ОТВЕТА" in result
        assert "казахский (қазақша)" in result
        assert "Отвечай на языке: казахский (қазақша)." in result
        assert "не переводи" in result
        assert "поясняя на языке ответа" in result


class TestLanguageBlockUzHi:
    """Uzbek and Hindi language blocks contain their respective names."""

    def test_uz_contains_uzbek(self) -> None:
        """language='uz' → prompt contains 'узбекский'."""
        hub = _build_test_hub()
        result = _prompt(hub, language="uz")

        assert "## ЯЗЫК ОТВЕТА" in result
        assert "узбекский" in result
        assert "oʻzbekcha" in result

    def test_hi_contains_hindi(self) -> None:
        """language='hi' → prompt contains 'хинди'."""
        hub = _build_test_hub()
        result = _prompt(hub, language="hi")

        assert "## ЯЗЫК ОТВЕТА" in result
        assert "хинди" in result
        # Devanagari script present in the LANGUAGE_NAMES value.
        assert "देवनागरी" in result


class TestLanguageBlockUnknownFallback:
    """Unknown language values fall back to the Russian block."""

    def test_unknown_language_falls_back_to_ru(
        self, monkeypatch: Any, caplog: Any
    ) -> None:
        """language='de' → falls back to ru rule (no exception, no 'казахский')."""
        hub = _build_test_hub()
        with caplog.at_level(logging.WARNING, logger="mechanic.agent.prompt"):
            result = _prompt(hub, language="de")

        assert "## ЯЗЫК ОТВЕТА" in result
        ru_msg = "Отвечай на языке вопроса пользователя (по умолчанию — русский)."
        assert ru_msg in result
        assert "казахский" not in result
        assert any("unknown language 'de'" in rec.message for rec in caplog.records)


class TestChatRequestValidation:
    """Pydantic model rejects invalid literal values."""

    def test_invalid_language_raises_validation_error(self) -> None:
        """ChatRequest(language='de') raises pydantic ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ChatRequest(message="hello", language="de")

    def test_valid_languages_accepted(self) -> None:
        """language='ru', 'kk', 'uz', 'hi' are all accepted."""
        for lang in ("ru", "kk", "uz", "hi"):
            req = ChatRequest(message="hello", language=lang)
            assert req.language == lang

    def test_none_language_accepted(self) -> None:
        """language=None is accepted (default)."""
        req = ChatRequest(message="hello")
        assert req.language is None
