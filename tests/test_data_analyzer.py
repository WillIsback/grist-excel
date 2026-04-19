"""Tests for core/data_analyzer.py — DataAnalyzer and DataProfile."""
import json
import pytest
import openpyxl
from pathlib import Path
from core.data_analyzer import DataAnalyzer, DataProfile


@pytest.fixture
def sample_xlsx(tmp_path) -> Path:
    """Create a minimal two-sheet Excel file for testing."""
    wb = openpyxl.Workbook()

    # Sheet 1: Employes
    ws1 = wb.active
    ws1.title = "Employes"
    ws1.append(["ID", "Nom", "Departement", "Salaire"])
    ws1.append([1, "Alice", "IT", 60000])
    ws1.append([2, "Bob", "RH", 45000])
    ws1.append([3, "Carol", "IT", 75000])

    # Sheet 2: Absences (references Employes.ID)
    ws2 = wb.create_sheet("Absences")
    ws2.append(["ID_Employe", "Date_Debut", "Duree_Jours"])
    ws2.append([1, "2024-01-10", 3])
    ws2.append([2, "2024-02-05", 1])

    path = tmp_path / "test.xlsx"
    wb.save(str(path))
    return path


class TestDataProfile:
    def test_sheets_extracted(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        assert "Employes" in profile.sheets
        assert "Absences" in profile.sheets

    def test_columns_extracted(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        assert profile.columns["Employes"] == ["ID", "Nom", "Departement", "Salaire"]
        assert profile.columns["Absences"] == ["ID_Employe", "Date_Debut", "Duree_Jours"]

    def test_numeric_stats_computed(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        sal_stats = profile.stats["Employes.Salaire"]
        assert sal_stats["min"] == 45000
        assert sal_stats["max"] == 75000
        assert sal_stats["avg"] == pytest.approx(60000.0)
        assert sal_stats["non_null"] == 3

    def test_categorical_stats_computed(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        dept_stats = profile.stats["Employes.Departement"]
        assert dept_stats["unique"] == 2
        assert "IT" in dept_stats["top"]
        assert dept_stats["non_null"] == 3

    def test_apparent_fk_detected(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        fk_targets = [fk["to"] for fk in profile.apparent_fk]
        assert any("Employes" in t for t in fk_targets)

    def test_markdown_summary_contains_sheet_headers(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        assert "Employes" in profile.markdown_summary
        assert "Absences" in profile.markdown_summary
        assert "Nom" in profile.markdown_summary
        assert "Departement" in profile.markdown_summary

    def test_as_prompt_context_returns_string(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        ctx = profile.as_prompt_context()
        assert isinstance(ctx, str)
        assert "sheets" in ctx.lower() or "Employes" in ctx

    def test_summary_tables_are_computed(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        assert profile.summary_tables
        summary = profile.summary_tables[0]
        assert summary["source_table"] == "Employes"
        assert summary["group_by"] == "Departement"
        assert summary["metric"] == "Salaire"
        assert summary["records"]

    def test_to_json_returns_valid_json(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        json_str = profile.to_json()
        parsed = json.loads(json_str)
        assert "sheets" in parsed
        assert "columns" in parsed
        assert "stats" in parsed
        assert "apparent_fk" in parsed
        assert "summary_tables" in parsed
        assert "Employes" in parsed["sheets"]
