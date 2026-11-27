"""
File:   test_prompt.py
Brief:  Tests for the language-aware system-prompt builder and ChatRequest model.
Author: Mistress-Lukutar
Date:   2026-11-27
Version: v0.1.1

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
from mechanic.config import Settings
from mechanic.services.chats import ChatStore
from mechanic.services.hub import ServiceHub

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


def _build_hub_with_chats(tmp_path: Path) -> ServiceHub:
    """Build a minimal ServiceHub with a fresh ChatStore at *tmp_path*.

    Args:
        tmp_path: pytest temporary directory.

    Returns:
        A :class:`~mechanic.services.hub.ServiceHub` whose ``chats`` attribute
        points to an empty :class:`~mechanic.services.chats.ChatStore`.
    """
    settings = Settings(_env_file=None, app_data_dir=REPO_ROOT / "data")
    base_hub = _build_test_hub()

    hub = ServiceHub(
        settings=settings,
        fleet=base_hub.fleet,
        ml=base_hub.ml,
        toir=base_hub.toir,
        rag=base_hub.rag,
        manifest=base_hub.manifest,
        ticket_log=base_hub.ticket_log,
        chats=ChatStore(tmp_path / "chats.db"),
        usage=base_hub.usage,
        alerts=base_hub.alerts,
        auth=base_hub.auth,
    )
    return hub


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


class TestLanguageBlockRu:
    """Default / explicit Russian language produces the question-language rule."""

    def test_default_ru_contains_question_language_rule(
        self, monkeypatch: Any
    ) -> None:
        """Default (language="ru") -> new unified block with the
        'последнего вопроса' rule and no 'казахский'."""
        hub = _build_test_hub()
        result = _prompt(hub)

        assert "## ЯЗЫК ОТВЕТА" in result
        assert "Отвечай на языке последнего вопроса механика" in result
        assert "по умолчанию русский." in result
        assert "казахский" not in result


class TestLanguageBlockKk:
    """Kazakh language produces the explicit target-language block."""

    def test_kk_contains_target_language(self) -> None:
        """language='kk' → prompt contains 'казахский (қазақша)' rule."""
        hub = _build_test_hub()
        result = _prompt(hub, language="kk")

        assert "## ЯЗЫК ОТВЕТА" in result
        assert "казахский (қазақша)" in result
        assert "по умолчанию казахский (қазақша)" in result
        assert "Отвечай на языке последнего вопроса механика" in result
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
        assert "Отвечай на языке последнего вопроса механика" in result
        assert "по умолчанию русский." in result
        assert "казахский" not in result
        assert any("unknown language 'de'" in rec.message for rec in caplog.records)


@pytest.mark.parametrize("lang", ("ru", "kk", "uz", "hi"))
class TestQuestionLanguageRuleForAllLanguages:
    """The new question-language rule appears for every UI language."""

    def test_all_languages_contain_question_language_rule(self, lang: str) -> None:
        """Every language code produces the 'последнего вопроса механика' line."""
        hub = _build_test_hub()
        result = _prompt(hub, language=lang)
        assert "Отвечай на языке последнего вопроса механика" in result


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


class TestSystemPromptContent:
    """Verify textual content of prompts/system.md after manual edits."""

    def test_ladder_separates_warning_from_low_confidence(
        self, monkeypatch: Any
    ) -> None:
        """The warning bullet and the low-confidence bullet are distinct."""
        from mechanic.agent.prompt import PROMPTS_DIR

        prompt_file = PROMPTS_DIR / "system.md"
        if not prompt_file.exists():
            pytest.skip("prompts/system.md not found")

        content = prompt_file.read_text(encoding="utf-8")

        # The low-confidence bullet must contain all three markers.
        low_conf_bullet_ok = (
            "пониженной `confidence`" in content
            and "чек-лист" in content
            and "Повторная запись НЕ нужна" in content
        )
        assert low_conf_bullet_ok, (
            "Low-confidence bullet must contain 'пониженной confidence', "
            "'чек-лист' and 'Повторная запись НЕ нужна'"
        )

        # The original warning bullet must still mention повторную запись.
        assert (
            "порекомендуй повторную запись" in content
        ), "Warning bullet must still contain 'порекомендуй повторную запись'"

    def test_ticket_only_after_mechanic_confirms(self) -> None:
        """The low-confidence bullet contains the confirmation phrase."""
        from mechanic.agent.prompt import PROMPTS_DIR

        prompt_file = PROMPTS_DIR / "system.md"
        if not prompt_file.exists():
            pytest.skip("prompts/system.md not found")

        content = prompt_file.read_text(encoding="utf-8")
        assert (
            "подтвердит или опровергнет" in content
        ), "Low-confidence bullet must contain 'подтвердит или опровергнет'"

    def test_bylo_stalo_rule_present(self) -> None:
        """The 'было — стало' format rule is present in the prompt."""
        from mechanic.agent.prompt import PROMPTS_DIR

        prompt_file = PROMPTS_DIR / "system.md"
        if not prompt_file.exists():
            pytest.skip("prompts/system.md not found")

        content = prompt_file.read_text(encoding="utf-8")
        assert (
            "было — стало" in content
        ), "The 'было — стало' comparison rule must be present"

    def test_check_failed_requires_equipment_fix(self) -> None:
        """The check_failed bullet requires equipment fix and bans improvisation."""
        from mechanic.agent.prompt import PROMPTS_DIR

        prompt_file = PROMPTS_DIR / "system.md"
        if not prompt_file.exists():
            pytest.skip("prompts/system.md not found")

        content = prompt_file.read_text(encoding="utf-8")
        assert (
            "сначала нужно восстановить запись" in content
        ), "check_failed bullet must contain 'сначала нужно восстановить запись'"
        assert (
            "повторить запись" in content
        ), "check_failed bullet must contain 'повторить запись'"
        assert (
            "НЕ придумывай" in content
        ), "check_failed bullet must ban equipment-procedure improvisation"
        assert (
            "осмотр" in content
        ), "check_failed bullet must mention alternative inspection option"


class TestPastDiscussions:
    """Tests for the past-discussions block in build_system_prompt."""

    def test_block_absent_without_history(self, tmp_path: Path) -> None:
        """Empty ChatStore → no «ПРОШЛЫЕ ОБСУЖДЕНИЯ» in the prompt."""
        hub = _build_hub_with_chats(tmp_path)
        result = _prompt(hub, "M333YK47", username="mech")

        assert "## ПРОШЛЫЕ ОБСУЖДЕНИЯ" not in result

    def test_block_lists_recent_conversations(self, tmp_path: Path) -> None:
        """Two conversations → prompt contains title, tail, and continuation rule."""
        hub = _build_hub_with_chats(tmp_path)
        conv = hub.chats.create_conversation(
            "mech", "M333YK47", title="Зазоры клапанов"
        )
        hub.chats.add_message(conv["id"], "user", "Какой зазор?")
        hub.chats.add_message(conv["id"], "assistant", "***REMOVED*** мм")

        result = _prompt(
            hub, "M333YK47", username="mech", conversation_id=None
        )

        assert "## ПРОШЛЫЕ ОБСУЖДЕНИЯ" in result
        assert "Зазоры клапанов" in result
        assert "***REMOVED*** мм" in result
        assert "на чём остановились" in result

    def test_block_excludes_current_conversation(self, tmp_path: Path) -> None:
        """Only one conversation → excluded when passed as current id."""
        hub = _build_hub_with_chats(tmp_path)
        conv = hub.chats.create_conversation(
            "mech", "M333YK47", title="Зазоры клапанов"
        )
        hub.chats.add_message(conv["id"], "user", "Какой зазор?")
        hub.chats.add_message(conv["id"], "assistant", "***REMOVED*** мм")

        result = _prompt(
            hub, "M333YK47", username="mech", conversation_id=conv["id"]
        )

        assert "Зазоры клапанов" not in result
        assert "## ПРОШЛЫЕ ОБСУЖДЕНИЯ" not in result


def test_prompts_dir_anchored_to_repo_root() -> None:
    """PROMPTS_DIR must resolve from the code location, not the CWD."""
    repo_root = Path(__file__).resolve().parents[2]
    from mechanic.agent.prompt import PROMPTS_DIR

    assert PROMPTS_DIR == repo_root / "prompts"
    assert (PROMPTS_DIR / "system.md").is_file()
