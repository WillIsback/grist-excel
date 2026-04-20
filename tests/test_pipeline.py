"""Tests for core/pipeline.py — PipelineOrchestrator."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.pipeline import PipelineOrchestrator, PipelineResult
from core.data_analyzer import DataProfile
from core.visual_intents import VisualIntentPlan
from core.insight_extractor import InsightEntry, InsightReport
from core.domain_classifier import ClassificationResult


SAMPLE_XLSX_PATH = "samples/employees_rh.xlsx"


def _mock_profile():
    """Create a minimal DataProfile for testing."""
    return DataProfile(
        sheets=["Employes", "Absences"],
        columns={
            "Employes": ["ID", "Nom", "Departement"],
            "Absences": ["ID_Employe", "Date_Debut"],
        },
        stats={},
        apparent_fk=[],
        markdown_summary="# Test",
        summary_tables=[{
            "name": "Corr_Employes_Departement_Salaire",
            "group_by": "Departement",
            "metric": "Salaire",
            "source_table": "Employes",
            "columns": [],
            "records": [],
        }],
    )


class TestPipelineResult:
    def test_to_dict_includes_all_stages(self):
        result = PipelineResult(
            profile=_mock_profile(),
            classification=MagicMock(),
            insights=MagicMock(),
            dashboard_plan=MagicMock(),
            errors=[],
        )
        d = result.to_dict()
        assert "profile" in d
        assert "classification" in d
        assert "insights" in d
        assert "dashboard_plan" in d

    def test_to_dict_includes_visual_intents(self):
        result = PipelineResult(
            profile=_mock_profile(),
            visual_intents=VisualIntentPlan(intents=[]),
        )
        d = result.to_dict()
        assert "visual_intents" in d

    def test_save_writes_json(self, tmp_path):
        result = PipelineResult(
            profile=_mock_profile(),
            classification=MagicMock(),
            insights=MagicMock(),
            dashboard_plan=MagicMock(),
            errors=[],
        )
        output_file = tmp_path / "result.json"
        result.save(str(output_file))
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "profile" in data


class TestPipelineOrchestrator:
    @pytest.fixture
    def mock_agents(self):
        """Mock all three LLM agents."""
        classifiers = {}
        extractors = {}
        composers = {}

        def mock_classify(profile):
            from core.domain_classifier import ClassificationResult
            result = ClassificationResult(
                archetype="HR", confidence=0.9,
                table_mapping={"employees": "Employes", "absences": "Absences"},
                params={"name_col": "Nom", "department_col": "Departement"},
            )
            classifiers["called"] = True
            return result

        def mock_extract(profile, classification, user_intent=None):
            from core.insight_extractor import InsightReport, InsightEntry
            report = InsightReport(insights=[
                InsightEntry(type="distribution", table="Employes", col="Departement",
                            finding="IT et RH concentrent les effectifs", priority=1),
            ])
            extractors["called"] = True
            return report

        def mock_compose(classification, insights, feature_plan=None, **kwargs):
            from core.dashboard_composer import DashboardPlan, Page, PageSection
            plan = DashboardPlan(pages=[
                Page(name="Dashboard RH", sections=[
                    PageSection(widget="chart", chart_type="bar", table="Employes",
                               x="Departement", y="Nom", agg="count",
                               title="IT et RH concentrent les effectifs"),
                ]),
            ])
            composers["called"] = True
            return plan

        return mock_classify, mock_extract, mock_compose, classifiers, extractors, composers

    def test_full_pipeline_runs_all_agents(self, mock_agents, monkeypatch, tmp_path):
        mock_classify, mock_extract, mock_compose, _, _, _ = mock_agents
        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        profile = _mock_profile()
        result = orchestrator.run(profile)

        assert isinstance(result, PipelineResult)
        assert result.classification is not None
        assert result.insights is not None
        assert result.dashboard_plan is not None
        assert len(result.errors) == 0

    def test_compose_receives_summary_tables(self, mock_agents, monkeypatch):
        mock_classify, mock_extract, _, _, _, _ = mock_agents
        received = {}

        def mock_compose(classification, insights, feature_plan=None, **kwargs):
            from core.dashboard_composer import DashboardPlan
            received.update(kwargs)
            return DashboardPlan(pages=[])

        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        orchestrator.run(_mock_profile())

        assert received["summary_tables"]
        assert received["summary_tables"][0]["name"] == "Corr_Employes_Departement_Salaire"

    def test_compose_receives_visual_intents(self, mock_agents, monkeypatch):
        mock_classify, mock_extract, _, _, _, _ = mock_agents
        received = {}

        def mock_compose(classification, insights, feature_plan=None, **kwargs):
            from core.dashboard_composer import DashboardPlan
            received.update(kwargs)
            return DashboardPlan(pages=[])

        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        orchestrator.run(_mock_profile())

        assert received["visual_intents"] is not None
        assert received["visual_intents"].intents

    def test_error_handling_continues_pipeline(self, mock_agents, monkeypatch):
        mock_classify, _, mock_compose, _, _, _ = mock_agents

        def failing_extract(profile, classification, user_intent=None):
            raise RuntimeError("LLM timeout")

        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", failing_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        profile = _mock_profile()
        result = orchestrator.run(profile)

        assert len(result.errors) == 1
        assert "LLM timeout" in result.errors[0]
        assert result.classification is not None
        assert result.insights is None
        assert result.dashboard_plan is None

    def test_run_from_file_analyzes_and_processes(self, mock_agents, monkeypatch, tmp_path):
        mock_classify, mock_extract, mock_compose, _, _, _ = mock_agents
        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        # Create a fake xlsx
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK\x03\x04fake")

        # Mock data_analyzer.analyze since we can't parse a fake xlsx
        profile = _mock_profile()
        monkeypatch.setattr(orchestrator.data_analyzer, "analyze", lambda _: profile)

        result = orchestrator.run_from_file(str(xlsx))

        assert isinstance(result, PipelineResult)
        assert result.classification is not None

    def test_save_output(self, mock_agents, monkeypatch, tmp_path):
        mock_classify, mock_extract, mock_compose, _, _, _ = mock_agents
        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        profile = _mock_profile()
        result = orchestrator.run(profile)

        output_dir = tmp_path / "output"
        result.save(str(output_dir))
        assert (output_dir / "pipeline_result.json").exists()


class TestPipelineCheckpoints:
    from unittest.mock import MagicMock

    def _mock_classification(self):
        from core.domain_classifier import ClassificationResult
        return ClassificationResult(
            archetype="HR", confidence=0.9,
            table_mapping={"employees": "Employes"}, params={},
        )

    def _mock_insights(self):
        from core.insight_extractor import InsightReport, InsightEntry
        return InsightReport(insights=[
            InsightEntry(type="distribution", table="Employes", col="Departement",
                         finding="IT domine", priority=1),
            InsightEntry(type="kpi", table="Employes", col="Salaire",
                         finding="salaire élevé", priority=2),
        ])

    def test_no_handler_runs_without_checkpoint(self):
        from unittest.mock import MagicMock, patch
        orchestrator = PipelineOrchestrator()
        profile = _mock_profile()
        with patch.object(orchestrator, "_classify", return_value=self._mock_classification()), \
             patch.object(orchestrator, "_extract", return_value=self._mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            result = orchestrator.run(profile)
        assert result.errors == []

    def test_handler_called_after_classification(self):
        from unittest.mock import MagicMock, patch
        from core.checkpoint import ClassificationFeedback, InsightFeedback
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="HR", user_intent=""
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[0, 1])

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()

        with patch.object(orchestrator, "_classify", return_value=self._mock_classification()), \
             patch.object(orchestrator, "_extract", return_value=self._mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            orchestrator.run(profile)

        handler.on_classification.assert_called_once()
        handler.on_insights.assert_called_once()

    def test_archetype_override_applied(self):
        from unittest.mock import MagicMock, patch
        from core.checkpoint import ClassificationFeedback, InsightFeedback
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="DECISIONNEL", user_intent=""
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[0])

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()

        with patch.object(orchestrator, "_classify", return_value=self._mock_classification()), \
             patch.object(orchestrator, "_extract", return_value=self._mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            result = orchestrator.run(profile)

        assert result.classification.archetype == "DECISIONNEL"

    def test_insight_selection_filters_report(self):
        from unittest.mock import MagicMock, patch
        from core.checkpoint import ClassificationFeedback, InsightFeedback
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="HR", user_intent=""
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[1])  # only index 1

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()
        captured_insights = []

        def fake_plan(p, c, insights, user_intent=None):
            captured_insights.append(insights)
            return MagicMock(features=[])

        with patch.object(orchestrator, "_classify", return_value=self._mock_classification()), \
             patch.object(orchestrator, "_extract", return_value=self._mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", side_effect=fake_plan), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            orchestrator.run(profile)

        assert len(captured_insights[0].insights) == 1
        assert captured_insights[0].insights[0].col == "Salaire"  # index 1

    def test_user_intent_passed_to_extract(self):
        from unittest.mock import MagicMock, patch
        from core.checkpoint import ClassificationFeedback, InsightFeedback
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="HR", user_intent="analyser le turnover"
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[0])

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()
        captured_kwargs = {}

        def fake_extract(p, c, user_intent=None):
            captured_kwargs["user_intent"] = user_intent
            return self._mock_insights()

        with patch.object(orchestrator, "_classify", return_value=self._mock_classification()), \
             patch.object(orchestrator, "_extract", side_effect=fake_extract), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            orchestrator.run(profile)

        assert captured_kwargs["user_intent"] == "analyser le turnover"


# ---------------------------------------------------------------------------
# Module-level helpers for run_from_insights tests
# ---------------------------------------------------------------------------

def _mock_classification_module():
    return ClassificationResult(
        archetype="HR",
        confidence=0.9,
        table_mapping={"employees": "Employes"},
        params={"name_col": "Nom"},
    )


def _mock_insights_module():
    return [
        InsightEntry(
            type="distribution",
            table="Employes",
            col="Departement",
            finding="IT concentre 45%",
            priority=1,
        )
    ]


def test_run_from_insights_skips_analyzer_and_classifier():
    """run_from_insights() must not call DataAnalyzer or DomainClassifier."""
    with (
        patch("core.pipeline.DataAnalyzer") as mock_analyzer,
        patch("core.pipeline.DomainClassifier") as mock_classifier,
        patch("core.pipeline.InsightExtractor"),
        patch("core.pipeline.ColumnRelevanceFilter"),
        patch("core.pipeline.FeatureEngineer"),
        patch("core.pipeline.NarrativeGenerator"),
        patch("core.pipeline.VisualIntentResolver"),
        patch("core.pipeline.DashboardComposer"),
        patch("core.pipeline.ReflexionValidator"),
    ):
        orchestrator = PipelineOrchestrator()
        profile = _mock_profile()
        classification = _mock_classification_module()
        insights = _mock_insights_module()

        result = orchestrator.run_from_insights(
            cached_profile=profile,
            cached_classification=classification,
            selected_insights=insights,
            intent="test intent",
        )

        mock_analyzer.return_value.analyze.assert_not_called()
        mock_classifier.return_value.classify.assert_not_called()
        assert result.profile is profile
        assert result.classification is classification


def test_run_from_insights_returns_pipeline_result():
    orchestrator = PipelineOrchestrator()
    orchestrator.relevance_filter = MagicMock()
    orchestrator.relevance_filter.filter.return_value = _mock_profile()
    orchestrator.insight_extractor = MagicMock()
    orchestrator.feature_engineer = MagicMock()
    orchestrator.feature_engineer.plan.return_value = MagicMock(features=[])
    orchestrator.narrative_generator = MagicMock()
    orchestrator.narrative_generator.generate.return_value = "summary"
    orchestrator.visual_intent_resolver = MagicMock()
    orchestrator.visual_intent_resolver.resolve.return_value = MagicMock(intents=[])
    orchestrator.composer = MagicMock()
    orchestrator.composer.compose.return_value = MagicMock(pages=[])

    result = orchestrator.run_from_insights(
        cached_profile=_mock_profile(),
        cached_classification=_mock_classification_module(),
        selected_insights=_mock_insights_module(),
        intent="turnover",
    )

    assert isinstance(result, PipelineResult)
    # InsightExtractor must not have been called
    orchestrator.insight_extractor.extract.assert_not_called()
