"""
File:   test_priority.py
Brief:  Tests for priority.suggest_urgency — deterministic urgency suggestion.
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0
"""

from __future__ import annotations

from shared.models import DiagnosticResult, DiagnosticStatus

from mechanic.services.priority import CRITICAL_CODES, suggest_urgency


def _make_diag(
    anomaly_type: str = "F08",
    anomaly_score: float | None = 0.76,
    confidence: float | None = 0.73,
    status: DiagnosticStatus = "anomaly",
) -> DiagnosticResult:
    """Build a DiagnosticResult for testing."""
    return DiagnosticResult(
        vehicle_id="M333YK47",
        session_id="S-0005",
        status=status,
        anomaly_type=anomaly_type,
        anomaly_score=anomaly_score,
        confidence=confidence,
        signal_quality="good",
        description="Test diagnostic result",
        model_version="v1.0",
    )


class TestPriorityHigh:
    """Test high urgency suggestions."""

    def test_high_f08_score_076_conf_073(self) -> None:
        """F08 score 0.76 conf 0.73 → high with correct rationale."""
        diag = _make_diag(anomaly_type="F08", anomaly_score=0.76, confidence=0.73)
        suggestion = suggest_urgency(diag, "Дизельная топливоподача")

        assert suggestion.urgency == "high"
        assert "Приоритет высокий" in suggestion.rationale
        assert "Дизельная топливоподача" in suggestion.rationale
        assert "F08" not in suggestion.rationale  # rationale uses title, not code
        assert "риск отказа в рейсе" in suggestion.rationale


class TestPriorityMedium:
    """Test medium urgency suggestions."""

    def test_medium_f01_score_05_conf_05(self) -> None:
        """F01 score 0.5 conf 0.5 → medium (critical code, moderate readings)."""
        diag = _make_diag(anomaly_type="F01", anomaly_score=0.5, confidence=0.5)
        suggestion = suggest_urgency(diag, "Газораспределительный механизм")

        assert suggestion.urgency == "medium"
        assert "Приоритет средний" in suggestion.rationale
        assert "критичный узел" in suggestion.rationale

    def test_medium_f12_score_085(self) -> None:
        """F12 score 0.85 → medium (non-critical but significant deviation)."""
        diag = _make_diag(anomaly_type="F12", anomaly_score=0.85, confidence=0.4)
        suggestion = suggest_urgency(diag, "Турбокомпрессор")

        assert suggestion.urgency == "medium"
        assert "Приоритет средний" in suggestion.rationale
        assert "значительно отклоняется" in suggestion.rationale


class TestPriorityLow:
    """Test low urgency suggestions."""

    def test_low_f05_score_055_conf_06(self) -> None:
        """F05 score 0.55 conf 0.6 → low (not critical, score < 0.8)."""
        diag = _make_diag(anomaly_type="F05", anomaly_score=0.55, confidence=0.6)
        suggestion = suggest_urgency(diag, "Система смазки")

        assert suggestion.urgency == "low"
        assert "Приоритет низкий" in suggestion.rationale


class TestPriorityNoneScoreConfidence:
    """Test handling of None anomaly_score and confidence."""

    def test_none_anomaly_score(self) -> None:
        """None anomaly_score does not crash and renders 'нет данных'."""
        diag = _make_diag(anomaly_type="F08", anomaly_score=None, confidence=0.9)
        suggestion = suggest_urgency(diag, "Дизельная топливоподача")

        assert suggestion.urgency == "high"  # confidence >= 0.75 triggers high
        assert "нет данных" in suggestion.rationale

    def test_none_confidence(self) -> None:
        """None confidence does not crash and renders 'нет данных'."""
        diag = _make_diag(anomaly_type="F08", anomaly_score=0.9, confidence=None)
        suggestion = suggest_urgency(diag, "Дизельная топливоподача")

        assert suggestion.urgency == "high"  # score >= 0.7 triggers high
        assert "нет данных" in suggestion.rationale

    def test_both_none(self) -> None:
        """Both None → low (both treated as 0.0, below thresholds)."""
        diag = _make_diag(anomaly_type="F05", anomaly_score=None, confidence=None)
        suggestion = suggest_urgency(diag, "Система зажигания")

        assert suggestion.urgency == "low"
        assert "нет данных" in suggestion.rationale


class TestCriticalCodes:
    """Verify CRITICAL_CODES set contents."""

    def test_critical_codes_set(self) -> None:
        """CRITICAL_CODES contains the expected fault codes."""
        expected = {"F01", "F02", "F03", "F08", "F09", "F14"}
        assert CRITICAL_CODES == expected

    def test_f05_not_critical(self) -> None:
        """F05 is not in CRITICAL_CODES."""
        assert "F05" not in CRITICAL_CODES

    def test_f12_not_critical(self) -> None:
        """F12 is not in CRITICAL_CODES."""
        assert "F12" not in CRITICAL_CODES
