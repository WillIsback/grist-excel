"""Pipeline Orchestrator — chains Agent 1 → 2 → 3 → 3.5 → 4 → 4.5.

Coordinates the full data-to-dashboard pipeline:
1. DataAnalyzer: Excel → DataProfile
2. DomainClassifier: DataProfile → ClassificationResult
3. InsightExtractor: DataProfile + Classification → InsightReport
3.5. FeatureEngineer: Profile + Classification + Insights → FeaturePlan
4. DashboardComposer: Classification + Insights + FeaturePlan → DashboardPlan
4.5. ReflexionValidator: DashboardPlan + Classification + Insights → Validated DashboardPlan

Handles errors gracefully — if one agent fails, subsequent agents
receive None and the pipeline records the error but continues.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.data_analyzer import DataAnalyzer, DataProfile
from core.domain_classifier import DomainClassifier, ClassificationResult
from core.insight_extractor import InsightExtractor, InsightReport
from core.dashboard_composer import DashboardComposer, DashboardPlan
from core.feature_engineer import FeatureEngineer, FeaturePlan
from core.reflexion import ReflexionValidator
from core.visual_intents import VisualIntentPlan, VisualIntentResolver
from core.checkpoint import CheckpointHandler, ClassificationFeedback, InsightFeedback
from core.column_relevance_filter import ColumnRelevanceFilter
from core.narrative_generator import NarrativeGenerator
from core.debug_utils import debug_print
from config import Settings


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    profile: DataProfile | None = None
    classification: ClassificationResult | None = None
    insights: InsightReport | None = None
    feature_plan: FeaturePlan | None = None
    narrative: str | None = None
    visual_intents: VisualIntentPlan | None = None
    dashboard_plan: DashboardPlan | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the pipeline result to a dict."""
        return {
            "profile": json.loads(self.profile.to_json()) if self.profile else None,
            "classification": self.classification.model_dump() if self.classification else None,
            "insights": self.insights.model_dump() if self.insights else None,
            "feature_plan": self.feature_plan.model_dump() if self.feature_plan else None,
            "visual_intents": self.visual_intents.model_dump() if self.visual_intents else None,
            "dashboard_plan": self.dashboard_plan.model_dump() if self.dashboard_plan else None,
            "errors": self.errors,
        }

    def save(self, output_dir: str) -> None:
        """Save the pipeline result to JSON.

        Accepts either a directory path (creates pipeline_result.json inside)
        or a file path ending in .json (writes directly to it).
        """
        p = Path(output_dir)
        if p.exists() and p.is_dir():
            output_file = p / "pipeline_result.json"
        elif output_dir.lower().endswith(".json"):
            p.parent.mkdir(parents=True, exist_ok=True)
            output_file = p
        else:
            p.mkdir(parents=True, exist_ok=True)
            output_file = p / "pipeline_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=str)


class PipelineOrchestrator:
    """Orchestrates the full data-to-dashboard pipeline."""

    def __init__(self, settings: Settings | None = None, checkpoint_handler: "CheckpointHandler | None" = None):
        self.settings = settings or Settings()
        self.debug = self.settings.DEBUG
        self.data_analyzer = DataAnalyzer(settings)
        self.classifier = DomainClassifier(settings)
        self.insight_extractor = InsightExtractor(settings)
        self.composer = DashboardComposer(settings)
        self.feature_engineer = FeatureEngineer(settings)
        self.visual_intent_resolver = VisualIntentResolver()
        self.checkpoint_handler = checkpoint_handler
        self.relevance_filter = ColumnRelevanceFilter(settings)
        self.narrative_generator = NarrativeGenerator(settings)

    def run(self, profile: DataProfile) -> PipelineResult:
        result = PipelineResult()
        result.profile = profile
        debug_print("Agent 1 — DataAnalyzer", profile, self.debug)

        try:
            result.classification = self._classify(profile)
            debug_print("Agent 2 — DomainClassifier", result.classification, self.debug)
        except Exception as e:
            result.errors.append(f"DomainClassifier failed: {e}")

        # Checkpoint 1: classification confirmation + user intent
        user_intent: str = ""
        if self.checkpoint_handler and result.classification is not None:
            try:
                feedback = self.checkpoint_handler.on_classification(result.classification, profile)
                if feedback.confirmed_archetype != result.classification.archetype:
                    result.classification = ClassificationResult(
                        archetype=feedback.confirmed_archetype,
                        confidence=result.classification.confidence,
                        table_mapping=result.classification.table_mapping,
                        params=result.classification.params,
                    )
                user_intent = feedback.user_intent
            except Exception as e:
                result.errors.append(f"Checkpoint 1 failed: {e}")

        # Agent 2.5: column relevance filter (only when intent provided)
        active_profile = profile
        if user_intent and result.classification is not None:
            try:
                active_profile = self.relevance_filter.filter(profile, user_intent)
                debug_print("Agent 2.5 — ColumnRelevanceFilter", active_profile, self.debug)
            except Exception as e:
                result.errors.append(f"ColumnRelevanceFilter failed: {e}")

        if result.classification is not None:
            try:
                result.insights = self._extract(
                    active_profile, result.classification,
                    user_intent=user_intent or None,
                )
                debug_print("Agent 3 — InsightExtractor", result.insights, self.debug)
            except Exception as e:
                result.errors.append(f"InsightExtractor failed: {e}")

        # Checkpoint 2: insight selection
        if self.checkpoint_handler and result.insights is not None:
            try:
                feedback2 = self.checkpoint_handler.on_insights(result.insights, profile)
                if feedback2.selected_indices is not None:
                    all_insights = result.insights.insights
                    selected = [
                        all_insights[i]
                        for i in feedback2.selected_indices
                        if i < len(all_insights)
                    ]
                    if selected:
                        result.insights = InsightReport(insights=selected)
                if feedback2.custom_focus:
                    user_intent = (
                        f"{user_intent} {feedback2.custom_focus}".strip()
                        if user_intent
                        else feedback2.custom_focus
                    )
            except Exception as e:
                result.errors.append(f"Checkpoint 2 failed: {e}")

        # Agent 3.5: Feature Engineering
        if result.classification is not None and result.insights is not None:
            try:
                result.feature_plan = self.feature_engineer.plan(
                    profile, result.classification, result.insights,
                    user_intent=user_intent or None,
                )
                debug_print("Agent 3.5 — FeatureEngineer", result.feature_plan, self.debug)
            except Exception as e:
                result.errors.append(f"FeatureEngineer failed: {e}")
                result.feature_plan = FeaturePlan(features=[])

        # Agent 3.6: Narrative Generation
        if result.classification is not None and result.insights is not None:
            try:
                result.narrative = self.narrative_generator.generate(
                    profile, result.classification, result.insights,
                    feature_plan=result.feature_plan,
                    user_intent=user_intent or None,
                )
                debug_print("Agent 3.6 — NarrativeGenerator", {"chars": len(result.narrative)}, self.debug)
            except Exception as e:
                result.errors.append(f"NarrativeGenerator failed: {e}")

        if result.classification is not None and result.insights is not None:
            try:
                result.visual_intents = self._resolve_visual_intents(
                    profile, result.classification, result.insights,
                    narrative=result.narrative,
                )
                debug_print("VisualIntentResolver", result.visual_intents, self.debug)
            except Exception as e:
                result.errors.append(f"VisualIntentResolver failed: {e}")

        if result.classification is not None and result.insights is not None:
            try:
                result.dashboard_plan = self._compose(
                    result.classification, result.insights, result.feature_plan,
                    raw_cols=profile.columns, stats=profile.stats,
                    summary_tables=profile.summary_tables,
                    visual_intents=result.visual_intents,
                    user_intent=user_intent or None,
                )
                debug_print("Agent 4 — DashboardComposer", result.dashboard_plan, self.debug)
            except Exception as e:
                result.errors.append(f"DashboardComposer failed: {e}")

        # Agent 4.5: Reflexion Validation
        if result.dashboard_plan is not None and result.classification is not None:
            try:
                raw_cols = profile.columns
                engineered_cols: dict[str, list[str]] = {}
                if result.feature_plan:
                    for f in result.feature_plan.features:
                        table_id = result.classification.table_mapping.get(f.table, f.table)
                        engineered_cols.setdefault(table_id, []).append(f.col_id)

                validator = ReflexionValidator(
                    raw_cols=raw_cols,
                    engineered_cols=engineered_cols,
                    table_mapping=result.classification.table_mapping,
                    summary_tables=profile.summary_tables,
                    visual_intents=result.visual_intents,
                )
                result.dashboard_plan = validator.validate(
                    result.dashboard_plan,
                    result.classification,
                    result.insights,
                    self.composer,
                )
                debug_print("Agent 4.5 — ReflexionValidator", result.dashboard_plan, self.debug)
            except Exception as e:
                result.errors.append(f"ReflexionValidator failed: {e}")

        return result

    def run_from_file(self, file_path: str) -> PipelineResult:
        """Run the full pipeline starting from an Excel file.

        Args:
            file_path: Path to the .xlsx file

        Returns:
            PipelineResult with all stages
        """
        profile = self.data_analyzer.analyze(file_path)
        return self.run(profile)

    def _classify(self, profile: DataProfile) -> ClassificationResult:
        """Run Agent 2: Domain Classification."""
        return self.classifier.classify(profile)

    def _extract(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        user_intent: str | None = None,
    ) -> InsightReport:
        """Run Agent 3: Insight Extraction."""
        return self.insight_extractor.extract(profile, classification, user_intent=user_intent)

    def _compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
        raw_cols: dict | None = None,
        stats: dict | None = None,
        summary_tables: list[dict[str, Any]] | None = None,
        visual_intents: VisualIntentPlan | None = None,
        user_intent: str | None = None,
    ) -> DashboardPlan:
        """Run Agent 4: Dashboard Composition."""
        return self.composer.compose(classification, insights, feature_plan,
                                     raw_cols=raw_cols, stats=stats,
                                     summary_tables=summary_tables,
                                     visual_intents=visual_intents,
                                     user_intent=user_intent)

    def _resolve_visual_intents(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
        narrative: str | None = None,
    ) -> VisualIntentPlan:
        """Resolve deterministic visual intents from existing pipeline outputs."""
        return self.visual_intent_resolver.resolve(profile, classification, insights, narrative=narrative)
