"""Tests pour core/grist_analyzer.py."""
import pytest
from unittest.mock import patch, MagicMock
from core.grist_analyzer import GristAnalyzer, GristDocumentInfo
from core.grist_api import GristAPI


@pytest.fixture
def mock_session():
    """Mock requests.Session."""
    with patch("requests.Session") as mock_session_cls:
        session = MagicMock()
        mock_session_cls.return_value = session
        yield session


@pytest.fixture
def grist_api(mock_session):
    """GristAPI avec orgId pré-chargé."""
    api = GristAPI("http://localhost:8484", "test-key")
    api._org_id = "2"
    return api


class TestGristDocumentInfo:
    """Tests pour GristDocumentInfo."""

    def test_init_with_tables(self):
        tables = [
            {"id": "Ventes", "label": "Ventes", "columns": [
                {"id": "id", "fields": {"type": "Integer"}},
                {"id": "Montant", "fields": {"type": "Numeric"}},
            ]},
        ]
        info = GristDocumentInfo("doc1", tables)
        assert info.doc_id == "doc1"
        assert "Ventes" in info.tables
        assert info.tables["Ventes"]["label"] == "Ventes"
        assert len(info.tables["Ventes"]["columns"]) == 2

    def test_get_table_names(self):
        tables = [
            {"id": "T1", "label": "T1", "columns": []},
            {"id": "T2", "label": "T2", "columns": []},
        ]
        info = GristDocumentInfo("doc1", tables)
        assert info.get_table_names() == ["T1", "T2"]

    def test_get_table(self):
        tables = [{"id": "T1", "label": "T1", "columns": []}]
        info = GristDocumentInfo("doc1", tables)
        table = info.get_table("T1")
        assert table["id"] == "T1"

    def test_get_table_missing(self):
        tables = [{"id": "T1", "label": "T1", "columns": []}]
        info = GristDocumentInfo("doc1", tables)
        assert info.get_table("Missing") == {}


class TestComputeStats:
    """Tests pour _compute_stats."""

    def test_stats_numeric_column(self):
        records = [
            {"fields": {"Amount": 100}},
            {"fields": {"Amount": 200}},
            {"fields": {"Amount": 300}},
        ]
        columns = [{"id": "Amount", "fields": {"type": "Numeric"}}]
        stats = GristAnalyzer._compute_stats(records, columns)
        assert stats["Amount"]["non_null_count"] == 3
        assert stats["Amount"]["unique_count"] == 3
        assert stats["Amount"]["min"] == 100
        assert stats["Amount"]["max"] == 300
        assert stats["Amount"]["avg"] == 200.0

    def test_stats_text_column(self):
        records = [
            {"fields": {"Status": "Active"}},
            {"fields": {"Status": "Inactive"}},
            {"fields": {"Status": "Active"}},
        ]
        columns = [{"id": "Status", "fields": {"type": "Text"}}]
        stats = GristAnalyzer._compute_stats(records, columns)
        assert stats["Status"]["non_null_count"] == 3
        assert stats["Status"]["unique_count"] == 2
        assert stats["Status"]["top_values"][0][0] == "Active"
        assert stats["Status"]["top_values"][0][1] == 2

    def test_stats_null_values(self):
        records = [
            {"fields": {"Val": 1}},
            {"fields": {"Val": None}},
            {"fields": {"Val": 3}},
        ]
        columns = [{"id": "Val", "fields": {"type": "Integer"}}]
        stats = GristAnalyzer._compute_stats(records, columns)
        assert stats["Val"]["null_count"] == 1
        assert stats["Val"]["non_null_count"] == 2

    def test_stats_empty_records(self):
        columns = [{"id": "X", "fields": {"type": "Text"}}]
        stats = GristAnalyzer._compute_stats([], columns)
        assert stats["X"]["non_null_count"] == 0


class TestGristAnalyzer:
    """Tests pour GristAnalyzer."""

    def test_analyze_fetches_structure_and_data(
        self, grist_api, mock_session
    ):
        """L'analyse récupère structure + records."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = [
            {  # get_tables
                "tables": [
                    {
                        "id": "Ventes",
                        "label": "Ventes",
                    }
                ]
            },
            {  # get_columns for Ventes
                "columns": [
                    {"id": "id", "fields": {"type": "Integer", "label": "id"}},
                    {"id": "Montant", "fields": {"type": "Numeric", "label": "Montant"}},
                ]
            },
            {  # get_records for Ventes
                "records": [
                    {"id": 1, "fields": {"id": 1, "Montant": 100}},
                    {"id": 2, "fields": {"id": 2, "Montant": 200}},
                ]
            },
        ]
        mock_session.request.return_value = mock_response

        analyzer = GristAnalyzer(grist_api)
        grist_api._workspace_id = 2
        info = analyzer.analyze("doc1")

        assert "Ventes" in info.tables
        assert len(info.tables["Ventes"]["records"]) == 2
        assert info.tables["Ventes"]["stats"]["Montant"]["min"] == 100
        assert info.tables["Ventes"]["stats"]["Montant"]["max"] == 200
