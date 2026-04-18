"""Tests for core/grist_importer.py - GristImporter."""
import pytest
from unittest.mock import MagicMock, patch, call
import pandas as pd
from core.grist_importer import GristImporter, _infer_grist_type
from core.grist_api import GristAPI, GristConnectionError


@pytest.fixture
def mock_api():
    api = MagicMock(spec=GristAPI)
    api.create_document.return_value = "new~abc123~1"
    return api


class TestGristImporter:
    def test_import_excel_creates_document(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        importer = GristImporter(mock_api)

        with patch("pandas.ExcelFile") as MockXls:
            mock_xls = MagicMock()
            mock_xls.sheet_names = ["Sheet1"]
            MockXls.return_value = mock_xls

            doc_id = importer.import_excel(str(xlsx))

            assert doc_id == "new~abc123~1"
            mock_api.create_document.assert_called_once()

    def test_import_excel_reads_all_sheets(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        importer = GristImporter(mock_api)

        mock_row = MagicMock()
        mock_row.__iter__ = MagicMock(return_value=iter(["A", "B"]))
        mock_row.__getitem__ = MagicMock(side_effect=lambda k: "val")
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df.columns = ["A", "B"]
        mock_df.iterrows.return_value = iter([(0, mock_row), (1, mock_row)])

        with patch("pandas.ExcelFile") as MockXls, \
             patch("pandas.read_excel", return_value=mock_df):
            mock_xls = MagicMock()
            mock_xls.sheet_names = ["Sheet1", "Sheet2"]
            MockXls.return_value = mock_xls

            importer.import_excel(str(xlsx))

            assert mock_api.create_table.call_count == 2
            assert mock_api.add_records.call_count == 2

    def test_raises_if_file_not_found(self, mock_api):
        importer = GristImporter(mock_api)

        with pytest.raises(FileNotFoundError):
            importer.import_excel("/nonexistent/path/file.xlsx")

    def test_raises_if_document_creation_fails(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        mock_api.create_document.side_effect = Exception("API error")
        importer = GristImporter(mock_api)

        with pytest.raises(GristConnectionError, match="creer|Impossible"):
            importer.import_excel(str(xlsx))


def test_salary_column_is_numeric_not_date():
    """Large integers must not be mis-typed as Date."""
    series = pd.Series([30739, 55872, 97639, 42000, 85000])
    assert _infer_grist_type(series) == "Numeric"


def test_integer_column_is_int():
    series = pd.Series([1, 2, 3, 4, 5])
    assert _infer_grist_type(series) == "Int"


def test_score_column_is_numeric_not_date():
    """Float scores (0.0–5.0 range) must not be mis-typed."""
    series = pd.Series([3.5, 4.0, 2.5, 5.0, 1.0])
    assert _infer_grist_type(series) == "Numeric"


def test_actual_date_string_column_is_date():
    series = pd.Series(["2024-01-15", "2023-06-30", "2022-12-01"])
    assert _infer_grist_type(series) in ("Date", "DateTime")


def test_boolean_column_is_toggle():
    series = pd.Series(["oui", "non", "oui", "oui"])
    assert _infer_grist_type(series) == "Toggle"
