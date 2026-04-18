"""Tests pour core/grist_updater.py."""
import pytest
import json
from unittest.mock import patch, MagicMock
from core.grist_updater import GristUpdater
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


class TestApplyFormula:
    """Tests pour l'application de formules."""

    def test_add_formula_column(self, grist_api, mock_session):
        """Ajouter une colonne avec formule via API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        updater = GristUpdater(grist_api)
        grist_api._workspace_id = 2

        config = {
            "formulas": [
                {
                    "table": "Ventes",
                    "column": "Total",
                    "type": "Numeric",
                    "formula": "@Montant * 1.20",
                    "label": "Total TTC",
                }
            ]
        }
        updater.apply_config("doc1", config)

        # Vérifier que add_columns a été appelé
        call_args = mock_session.request.call_args
        assert call_args[0][0] == "POST"
        assert "/api/docs/doc1/tables/Ventes/columns" in call_args[0][1]
        payload = call_args[1]["json"]
        assert payload["columns"][0]["id"] == "Total"
        assert payload["columns"][0]["fields"]["formula"] == "@Montant * 1.20"
        assert payload["columns"][0]["fields"]["isFormula"] is True

    def test_formula_summary(self, grist_api, mock_session):
        """Le résumé compte les formules appliquées."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        updater = GristUpdater(grist_api)
        grist_api._workspace_id = 2

        config = {
            "formulas": [
                {"table": "Ventes", "column": "Total", "type": "Numeric", "formula": "@A * 2"},
                {"table": "Ventes", "column": "Remise", "type": "Numeric", "formula": "@Total * 0.9"},
            ]
        }
        summary = updater.apply_config("doc1", config)

        assert summary["formulas_applied"] == 2
        assert len(summary["errors"]) == 0


class TestApplyColumnChange:
    """Tests pour les changements de colonnes."""

    def test_change_column_to_choice(self, grist_api, mock_session):
        """Changer une colonne en type Choice."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response

        updater = GristUpdater(grist_api)
        grist_api._workspace_id = 2

        config = {
            "columnChanges": [
                {
                    "table": "Ventes",
                    "column": "Statut",
                    "newType": "Choice",
                    "choices": ["Payé", "En attente", "Annulé"],
                }
            ]
        }
        summary = updater.apply_config("doc1", config)

        assert summary["column_changes_applied"] == 1
        call_args = mock_session.request.call_args
        payload = call_args[1]["json"]
        assert payload["columns"][0]["fields"]["type"] == "Choice"
        widget_opts = json.loads(
            payload["columns"][0]["fields"]["widgetOptions"]
        )
        assert "choices" in widget_opts
        assert "Payé" in widget_opts["choices"]


class TestPrintRecommendations:
    """Tests pour l'affichage des recommandations."""

    def test_print_empty_recommendations(self, capsys):
        """Pas de recommandation → message vide."""
        config = {"recommendations": []}
        GristUpdater.print_recommendations(config)
        captured = capsys.readouterr()
        assert "Aucune recommandation" in captured.out

    def test_print_recommendations_shows_list(self, capsys):
        """Affiche la liste des recommandations."""
        config = {
            "recommendations": [
                {
                    "widget": "Chart",
                    "description": "Graphique des ventes par mois",
                    "table": "Ventes",
                    "x": "Mois",
                    "y": "Montant",
                    "aggregation": "sum",
                }
            ]
        }
        GristUpdater.print_recommendations(config)
        captured = capsys.readouterr()
        assert "Chart" in captured.out
        assert "Graphique des ventes par mois" in captured.out
        assert "Ventes" in captured.out


class TestNormalizeType:
    """Tests pour la normalisation des types (via GristAPI.normalize_grist_type)."""

    def test_normalize_integer(self):
        assert GristAPI.normalize_grist_type("Integer") == "Integer"
        assert GristAPI.normalize_grist_type("Int") == "Integer"

    def test_normalize_numeric(self):
        assert GristAPI.normalize_grist_type("Numeric") == "Numeric"
        assert GristAPI.normalize_grist_type("Float") == "Numeric"

    def test_normalize_text(self):
        assert GristAPI.normalize_grist_type("Text") == "Text"

    def test_normalize_toggle(self):
        assert GristAPI.normalize_grist_type("Toggle") == "Toggle"
        assert GristAPI.normalize_grist_type("Bool") == "Toggle"

    def test_normalize_unknown(self):
        assert GristAPI.normalize_grist_type("UnknownType") == "UnknownType"
