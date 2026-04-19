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
