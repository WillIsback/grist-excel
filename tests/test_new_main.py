"""Tests for the new main.py --input xlsx CLI."""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call


def _make_pipeline_result():
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport
    from core.dashboard_composer import DashboardPlan, Page, PageSection
    from core.pipeline import PipelineResult
    from core.data_analyzer import DataProfile

    profile = DataProfile(
        sheets=["Employes"],
        columns={"Employes": ["Nom", "Departement"]},
        stats={},
        apparent_fk=[],
        markdown_summary="",
    )
    classification = ClassificationResult(
        archetype="HR", confidence=0.91,
        table_mapping={"employees": "Employes"},
        params={"name_col": "Nom"},
    )
    insights = InsightReport(insights=[])
    plan = DashboardPlan(pages=[
        Page(name="Dashboard", sections=[
            PageSection(widget="table", table="Employes", title="Tableau"),
        ]),
    ])
    return PipelineResult(
        profile=profile,
        classification=classification,
        insights=insights,
        dashboard_plan=plan,
        errors=[],
    )


class TestNewMain:
    def test_dry_run_prints_plan_without_upload(self, tmp_path, capsys):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        result = _make_pipeline_result()

        with patch("main.DataAnalyzer") as MockDA, \
             patch("main.PipelineOrchestrator") as MockPO, \
             patch("main.GristImporter") as MockGI, \
             patch("main.ArchetypeEngine") as MockAE, \
             patch("argparse.ArgumentParser") as MockParser:
            MockDA.return_value.analyze.return_value = result.profile
            MockPO.return_value.run.return_value = result

            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = MagicMock(
                input=str(xlsx),
                output=str(tmp_path),
                dry_run=True,
            )
            MockParser.return_value = mock_parser

            from main import main
            main()

        MockGI.return_value.import_excel.assert_not_called()
        MockAE.return_value.apply.assert_not_called()
        captured = capsys.readouterr()
        assert "DashboardPlan" in captured.out or "pages" in captured.out

    def test_full_run_calls_importer_and_engine(self, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        result = _make_pipeline_result()

        with patch("main.DataAnalyzer") as MockDA, \
             patch("main.PipelineOrchestrator") as MockPO, \
             patch("main.GristImporter") as MockGI, \
             patch("main.ArchetypeEngine") as MockAE, \
             patch("main.GristAPI"), \
             patch("argparse.ArgumentParser") as MockParser:
            MockDA.return_value.analyze.return_value = result.profile
            MockPO.return_value.run.return_value = result
            MockGI.return_value.import_excel.return_value = "new~doc~1"
            MockAE.return_value.apply.return_value = ["Dashboard"]

            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = MagicMock(
                input=str(xlsx),
                output=str(tmp_path),
                dry_run=False,
            )
            MockParser.return_value = mock_parser

            from main import main
            main()

        MockGI.return_value.import_excel.assert_called_once_with(str(xlsx))
        MockAE.return_value.apply.assert_called_once()

    def test_pipeline_errors_printed_but_continue(self, tmp_path, capsys):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        result = _make_pipeline_result()
        result.errors = ["DomainClassifier failed: timeout"]

        with patch("main.DataAnalyzer") as MockDA, \
             patch("main.PipelineOrchestrator") as MockPO, \
             patch("main.GristImporter") as MockGI, \
             patch("main.ArchetypeEngine") as MockAE, \
             patch("main.GristAPI"), \
             patch("argparse.ArgumentParser") as MockParser:
            MockDA.return_value.analyze.return_value = result.profile
            MockPO.return_value.run.return_value = result
            MockGI.return_value.import_excel.return_value = "new~doc~1"
            MockAE.return_value.apply.return_value = []

            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = MagicMock(
                input=str(xlsx),
                output=str(tmp_path),
                dry_run=False,
            )
            MockParser.return_value = mock_parser

            from main import main
            main()

        captured = capsys.readouterr()
        assert "DomainClassifier failed" in captured.out

    def test_missing_input_file_exits(self, capsys):
        from main import main
        import sys
        with patch("argparse.ArgumentParser") as MockParser:
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = MagicMock(
                input="/nonexistent/path/test.xlsx",
                output="./output/",
                dry_run=False,
            )
            MockParser.return_value = mock_parser
            with pytest.raises(SystemExit):
                main()
        captured = capsys.readouterr()
        assert "introuvable" in captured.out

    def test_cli_requires_input_arg(self):
        import sys
        with patch("argparse.ArgumentParser") as MockParser:
            mock_parser = MagicMock()
            # Simulate missing required --input argument
            mock_parser.parse_args.side_effect = SystemExit(2)
            MockParser.return_value = mock_parser
            from main import main
            with pytest.raises(SystemExit):
                main()

    def test_output_dir_created(self, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        result = _make_pipeline_result()
        output_dir = tmp_path / "out"

        with patch("main.DataAnalyzer") as MockDA, \
             patch("main.PipelineOrchestrator") as MockPO, \
             patch("argparse.ArgumentParser") as MockParser:
            MockDA.return_value.analyze.return_value = result.profile
            MockPO.return_value.run.return_value = result

            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = MagicMock(
                input=str(xlsx),
                output=str(output_dir),
                dry_run=True,
            )
            MockParser.return_value = mock_parser

            from main import main
            main()

        assert output_dir.exists()
