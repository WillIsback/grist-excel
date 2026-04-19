"""Tests for core/pipeline.py — PipelineOrchestrator."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.pipeline import PipelineOrchestrator, PipelineResult
from core.data_analyzer import DataProfile


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

        def mock_extract(profile, classification):
            from core.insight_extractor import InsightReport, InsightEntry
            report = InsightReport(insights=[
                InsightEntry(type="distribution", table="Employes", col="Departement",
                            finding="IT et RH concentrent les effectifs", priority=1),
            ])
            extractors["called"] = True
            return report

        def mock_compose(classification, insights, feature_plan=None):
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

    def test_error_handling_continues_pipeline(self, mock_agents, monkeypatch):
        mock_classify, _, mock_compose, _, _, _ = mock_agents

        def failing_extract(profile, classification):
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
