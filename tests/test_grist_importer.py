"""Tests for core/grist_importer.py - GristImporter."""
import pytest
from unittest.mock import MagicMock, patch
from core.grist_importer import GristImporter
from core.grist_api import GristAPI, GristConnectionError


@pytest.fixture
def mock_api():
    api = MagicMock(spec=GristAPI)
    api.upload_excel.return_value = "new~abc123~1"
    api.get_tables.return_value = [
        {"id": "Employes", "fields": {}},
        {"id": "Absences", "fields": {}},
    ]
    return api


class TestGristImporter:
    def test_import_excel_returns_doc_id(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        importer = GristImporter(mock_api)

        doc_id = importer.import_excel(str(xlsx))

        assert doc_id == "new~abc123~1"

    def test_calls_upload_then_get_tables(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        importer = GristImporter(mock_api)

        importer.import_excel(str(xlsx))

        mock_api.upload_excel.assert_called_once_with(str(xlsx))
        mock_api.get_tables.assert_called_once_with("new~abc123~1")

    def test_raises_if_no_tables_after_import(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        mock_api.get_tables.return_value = []
        importer = GristImporter(mock_api)

        with pytest.raises(GristConnectionError) as exc_info:
            importer.import_excel(str(xlsx))
        assert "aucune table" in str(exc_info.value).lower()

    def test_raises_if_file_not_found(self, mock_api):
        importer = GristImporter(mock_api)

        with pytest.raises(FileNotFoundError):
            importer.import_excel("/nonexistent/path/file.xlsx")
