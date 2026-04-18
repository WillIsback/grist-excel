"""Tests pour core/schema_analyzer.py."""
import pytest
import json
from core.grist_analyzer import GristDocumentInfo
from core.schema_analyzer import SchemaAnalyzer, GRIST_ANALYZER_SYSTEM_PROMPT


@pytest.fixture
def sample_document_info():
    """Document Grist de test avec une table Ventes."""
    tables = [
        {
            "id": "Ventes",
            "label": "Ventes",
            "columns": [
                {"id": "id", "fields": {"type": "Integer"}},
                {"id": "Date", "fields": {"type": "Date"}},
                {"id": "Montant", "fields": {"type": "Numeric"}},
                {"id": "Statut", "fields": {"type": "Text"}},
            ],
            "records": [
                {"id": 1, "fields": {"id": 1, "Date": 1704067200000, "Montant": 1500.50, "Statut": "Payé"}},
                {"id": 2, "fields": {"id": 2, "Date": 1704153600000, "Montant": 2300.00, "Statut": "En attente"}},
                {"id": 3, "fields": {"id": 3, "Date": 1704240000000, "Montant": 890.25, "Statut": "Payé"}},
            ],
            "stats": {
                "Montant": {
                    "non_null_count": 3,
                    "null_count": 0,
                    "unique_count": 3,
                    "min": 890.25,
                    "max": 2300.00,
                    "avg": 1563.58,
                },
                "Statut": {
                    "non_null_count": 3,
                    "null_count": 0,
                    "unique_count": 2,
                    "top_values": [["Payé", 2], ["En attente", 1]],
                },
            },
        }
    ]
    return GristDocumentInfo("doc123", tables)


class TestSystemPrompt:
    """Tests pour le prompt système."""

    def test_prompt_exists(self):
        assert GRIST_ANALYZER_SYSTEM_PROMPT is not None
        assert len(GRIST_ANALYZER_SYSTEM_PROMPT) > 100

    def test_prompt_contains_grist_formulas(self):
        prompt = GRIST_ANALYZER_SYSTEM_PROMPT
        assert "Grist" in prompt
        assert "formula" in prompt.lower()

    def test_prompt_contains_output_format(self):
        prompt = GRIST_ANALYZER_SYSTEM_PROMPT
        assert "formulas" in prompt
        assert "columnChanges" in prompt
        assert "recommendations" in prompt


class TestSchemaAnalyzer:
    """Tests pour SchemaAnalyzer."""

    def test_build_prompt_includes_tables(
        self, sample_document_info
    ):
        """Le prompt inclut les noms de tables."""
        analyzer = SchemaAnalyzer(
            sample_document_info,
            "Crée un dashboard de ventes"
        )
        prompt = analyzer.build_prompt()
        assert "Ventes" in prompt
        assert "doc123" in prompt

    def test_build_prompt_includes_columns(
        self, sample_document_info
    ):
        """Le prompt inclut les colonnes avec types."""
        analyzer = SchemaAnalyzer(
            sample_document_info,
            "Dashboard"
        )
        prompt = analyzer.build_prompt()
        assert "Montant" in prompt
        assert "Numeric" in prompt
        assert "Date" in prompt

    def test_build_prompt_includes_stats(
        self, sample_document_info
    ):
        """Le prompt inclut les statistiques."""
        analyzer = SchemaAnalyzer(
            sample_document_info,
            "Dashboard"
        )
        prompt = analyzer.build_prompt()
        assert "Min:" in prompt
        assert "Max:" in prompt
        assert "Avg:" in prompt
        assert "Unique:" in prompt

    def test_build_prompt_includes_samples(
        self, sample_document_info
    ):
        """Le prompt inclut les échantillons de records."""
        analyzer = SchemaAnalyzer(
            sample_document_info,
            "Dashboard"
        )
        prompt = analyzer.build_prompt()
        assert "1500.5" in prompt
        assert "Payé" in prompt

    def test_build_prompt_includes_user_request(
        self, sample_document_info
    ):
        """Le prompt inclut la request utilisateur."""
        analyzer = SchemaAnalyzer(
            sample_document_info,
            "Crée un dashboard de ventes avec graphiques"
        )
        prompt = analyzer.build_prompt()
        assert "dashboard de ventes" in prompt

    def test_build_messages_format(
        self, sample_document_info
    ):
        """Les messages ont le format système + utilisateur."""
        analyzer = SchemaAnalyzer(
            sample_document_info,
            "Test request"
        )
        messages = analyzer.build_messages()
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "Test request" in messages[1]["content"]

    def test_build_prompt_multi_table(
        self, sample_document_info
    ):
        """Le prompt gère plusieurs tables."""
        sample_document_info.tables["Clients"] = {
            "id": "Clients",
            "label": "Clients",
            "columns": [
                {"id": "id", "fields": {"type": "Integer"}},
                {"id": "Nom", "fields": {"type": "Text"}},
            ],
            "records": [{"id": 1, "fields": {"id": 1, "Nom": "TechCorp"}}],
            "stats": {},
        }
        analyzer = SchemaAnalyzer(
            sample_document_info,
            "Dashboard"
        )
        prompt = analyzer.build_prompt()
        assert "Ventes" in prompt
        assert "Clients" in prompt
