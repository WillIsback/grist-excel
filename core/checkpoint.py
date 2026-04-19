# core/checkpoint.py
"""Checkpoint handlers for interactive pipeline steering."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from pydantic import BaseModel

from core.domain_classifier import ArchetypeLiteral

if TYPE_CHECKING:
    from core.data_analyzer import DataProfile
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport


class ClassificationFeedback(BaseModel):
    confirmed_archetype: ArchetypeLiteral
    user_intent: str  # empty string = no intent provided


class InsightFeedback(BaseModel):
    selected_indices: list[int]  # indices into InsightReport.insights
    custom_focus: str | None = None


@runtime_checkable
class CheckpointHandler(Protocol):
    def on_classification(
        self, result: "ClassificationResult", profile: "DataProfile"
    ) -> ClassificationFeedback: ...

    def on_insights(
        self, report: "InsightReport", profile: "DataProfile"
    ) -> InsightFeedback: ...


ARCHETYPE_CHOICES = ["HR", "DECISIONNEL", "SUPPORT", "STUDENT", "SI", "PROJECT", "GENERIC"]


class CLICheckpointHandler:
    """Interactive CLI checkpoint handler using stdin/stdout."""

    def on_classification(
        self, result: "ClassificationResult", profile: "DataProfile"
    ) -> ClassificationFeedback:
        print(f"\nArchetype detected: {result.archetype} (confidence: {result.confidence:.2f})")
        print("Tables mapped:")
        for role, table in result.table_mapping.items():
            col_count = len(profile.columns.get(table, []))
            print(f"  {role} → \"{table}\"   [{col_count} cols]")

        choices_str = "/".join(ARCHETYPE_CHOICES)
        archetype_input = input(
            f"\nConfirm archetype? [{choices_str}] (enter=keep): "
        ).strip().upper()
        confirmed = (
            archetype_input
            if archetype_input in ARCHETYPE_CHOICES
            else result.archetype
        )

        user_intent = input("What do you want to analyze? (enter=skip): ").strip()

        return ClassificationFeedback(
            confirmed_archetype=cast(ArchetypeLiteral, confirmed),
            user_intent=user_intent,
        )

    def on_insights(
        self, report: "InsightReport", profile: "DataProfile"
    ) -> InsightFeedback:
        print("\nInsights found — select what matters to you:\n")
        selected: list[int] = []

        for i, entry in enumerate(report.insights):
            stats_line = self._format_stats(entry.table, entry.col, profile)
            print(f"[{i + 1}] {entry.type} — {entry.table}.{entry.col}")
            print(f"    {entry.finding}")
            if stats_line:
                print(f"    {stats_line}")
            answer = input("    Include? [Y/n]: ").strip().lower()
            if answer != "n":
                selected.append(i)

        custom_input = input("\nCustom focus to add? (enter=skip): ").strip()
        custom_focus = custom_input if custom_input else None

        if not selected:
            print("Warning: no insights selected — dashboard will be minimal.")

        return InsightFeedback(selected_indices=selected, custom_focus=custom_focus)

    def _format_stats(self, table: str, col: str, profile: "DataProfile") -> str:
        key = f"{table}.{col}"
        stats = profile.stats.get(key, {})
        if not stats:
            return ""
        if "top" in stats:
            return "Top: " + ", ".join(str(v) for v in stats["top"][:4])
        if "min" in stats:
            return f"min={stats['min']:.0f}  max={stats['max']:.0f}  avg={stats['avg']:.0f}"
        return ""
