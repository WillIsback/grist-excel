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
from core.debug_utils import debug_print
from config import Settings


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    profile: DataProfile | None = None
    classification: ClassificationResult | None = None
    insights: InsightReport | None = None
    feature_plan: FeaturePlan | None = None
    dashboard_plan: DashboardPlan | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the pipeline result to a dict."""
        return {
            "profile": json.loads(self.profile.to_json()) if self.profile else None,
            "classification": self.classification.model_dump() if self.classification else None,
            "insights": self.insights.model_dump() if self.insights else None,
            "feature_plan": self.feature_plan.model_dump() if self.feature_plan else None,
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

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.debug = self.settings.DEBUG
        self.data_analyzer = DataAnalyzer(settings)
        self.classifier = DomainClassifier(settings)
        self.insight_extractor = InsightExtractor(settings)
        self.composer = DashboardComposer(settings)
        self.feature_engineer = FeatureEngineer(settings)

    def run(self, profile: DataProfile) -> PipelineResult:
        """Run the full pipeline on a DataProfile.

        Args:
            profile: DataProfile from Agent 1

        Returns:
            PipelineResult with all stages
        """
        result = PipelineResult()
        result.profile = profile
        debug_print("Agent 1 — DataAnalyzer", profile, self.debug)

        try:
            result.classification = self._classify(profile)
            debug_print("Agent 2 — DomainClassifier", result.classification, self.debug)
        except Exception as e:
            result.errors.append(f"DomainClassifier failed: {e}")

        if result.classification is not None:
            try:
                result.insights = self._extract(profile, result.classification)
                debug_print("Agent 3 — InsightExtractor", result.insights, self.debug)
            except Exception as e:
                result.errors.append(f"InsightExtractor failed: {e}")

        # Agent 3.5: Feature Engineering
        if result.classification is not None and result.insights is not None:
            try:
                result.feature_plan = self.feature_engineer.plan(
                    profile, result.classification, result.insights
                )
                debug_print("Agent 3.5 — FeatureEngineer", result.feature_plan, self.debug)
            except Exception as e:
                result.errors.append(f"FeatureEngineer failed: {e}")
                result.feature_plan = FeaturePlan(features=[])

        if result.classification is not None and result.insights is not None:
            try:
                result.dashboard_plan = self._compose(
                    result.classification, result.insights, result.feature_plan
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
    ) -> InsightReport:
        """Run Agent 3: Insight Extraction."""
        return self.insight_extractor.extract(profile, classification)

    def _compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
    ) -> DashboardPlan:
        """Run Agent 4: Dashboard Composition."""
        return self.composer.compose(classification, insights, feature_plan)
