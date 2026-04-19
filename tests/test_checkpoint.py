import pytest
from pydantic import ValidationError
from core.checkpoint import ClassificationFeedback, InsightFeedback


def test_classification_feedback_valid():
    fb = ClassificationFeedback(confirmed_archetype="HR", user_intent="pourquoi turnover élevé")
    assert fb.confirmed_archetype == "HR"
    assert fb.user_intent == "pourquoi turnover élevé"


def test_classification_feedback_empty_intent():
    fb = ClassificationFeedback(confirmed_archetype="GENERIC", user_intent="")
    assert fb.user_intent == ""


def test_classification_feedback_invalid_archetype():
    with pytest.raises(ValidationError):
        ClassificationFeedback(confirmed_archetype="INVALID", user_intent="test")


def test_insight_feedback_valid():
    fb = InsightFeedback(selected_indices=[0, 2, 4])
    assert fb.selected_indices == [0, 2, 4]
    assert fb.custom_focus is None


def test_insight_feedback_with_focus():
    fb = InsightFeedback(selected_indices=[1], custom_focus="analyse par ancienneté")
    assert fb.custom_focus == "analyse par ancienneté"


from core.checkpoint import CLICheckpointHandler, CheckpointHandler
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightEntry


def _make_profile():
    return DataProfile(
        sheets=["Employés"],
        columns={"Employés": ["ID", "Département", "Salaire"]},
        stats={
            "Employés.Département": {"non_null": 45, "null": 0, "unique": 4, "top": ["IT", "Finance", "Ops", "RH"]},
            "Employés.Salaire": {"non_null": 45, "null": 0, "unique": 45, "min": 30000.0, "max": 95000.0, "avg": 57000.0},
        },
        apparent_fk=[],
        markdown_summary="",
    )


def _make_classification():
    return ClassificationResult(
        archetype="HR",
        confidence=0.87,
        table_mapping={"employees": "Employés"},
        params={},
    )


def _make_insights():
    return InsightReport(insights=[
        InsightEntry(type="distribution", table="Employés", col="Département",
                     finding="IT concentre 45% des effectifs", priority=1),
        InsightEntry(type="outlier", table="Employés", col="Salaire",
                     finding="Salaires max élevés en Finance", priority=2),
    ])


def test_cli_handler_implements_protocol():
    handler = CLICheckpointHandler()
    assert isinstance(handler, CheckpointHandler)


def test_on_classification_keeps_archetype_on_enter(monkeypatch):
    handler = CLICheckpointHandler()
    monkeypatch.setattr("builtins.input", lambda _: "")
    fb = handler.on_classification(_make_classification(), _make_profile())
    assert fb.confirmed_archetype == "HR"
    assert fb.user_intent == ""


def test_on_classification_overrides_archetype(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["DECISIONNEL", "analyse des coûts par département"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_classification(_make_classification(), _make_profile())
    assert fb.confirmed_archetype == "DECISIONNEL"
    assert fb.user_intent == "analyse des coûts par département"


def test_on_classification_ignores_invalid_archetype(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["NOTVALID", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_classification(_make_classification(), _make_profile())
    assert fb.confirmed_archetype == "HR"  # falls back to original


def test_on_insights_selects_all_on_y(monkeypatch):
    handler = CLICheckpointHandler()
    monkeypatch.setattr("builtins.input", lambda _: "")  # enter = keep (default Y)
    fb = handler.on_insights(_make_insights(), _make_profile())
    assert fb.selected_indices == [0, 1]
    assert fb.custom_focus is None


def test_on_insights_deselects_on_n(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["n", "", ""])  # skip first, keep second, no custom focus
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_insights(_make_insights(), _make_profile())
    assert fb.selected_indices == [1]


def test_on_insights_captures_custom_focus(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["", "", "analyse par ancienneté"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_insights(_make_insights(), _make_profile())
    assert fb.custom_focus == "analyse par ancienneté"


def test_format_stats_categorical():
    handler = CLICheckpointHandler()
    profile = _make_profile()
    result = handler._format_stats("Employés", "Département", profile)
    assert "IT" in result


def test_format_stats_numeric():
    handler = CLICheckpointHandler()
    profile = _make_profile()
    result = handler._format_stats("Employés", "Salaire", profile)
    assert "30000" in result and "95000" in result


def test_format_stats_missing_key():
    handler = CLICheckpointHandler()
    profile = _make_profile()
    result = handler._format_stats("Employés", "NonExistent", profile)
    assert result == ""
