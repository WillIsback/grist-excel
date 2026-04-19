"""Checkpoint handlers for interactive pipeline steering."""
from __future__ import annotations

from pydantic import BaseModel

from core.domain_classifier import ArchetypeLiteral


class ClassificationFeedback(BaseModel):
    confirmed_archetype: ArchetypeLiteral
    user_intent: str  # empty string = no intent provided


class InsightFeedback(BaseModel):
    selected_indices: list[int]  # indices into InsightReport.insights
    custom_focus: str | None = None
