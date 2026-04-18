"""Tests pour main.py - CLI du nouvel analyseur Grist."""
import pytest
import json
from unittest.mock import patch, MagicMock, Mock
from pathlib import Path


class TestValidateDocId:
    """Tests pour validate_doc_id."""

    @patch("core.grist_api.GristAPI.get_tables")
    def test_valid_doc_id(self, mock_get_tables):
        from main import validate_doc_id
        from core.grist_api import GristAPI

        mock_get_tables.return_value = [{"id": "T1"}]
        api = GristAPI("http://localhost:8484", "test-key")
        assert validate_doc_id(api, "doc1") is True

    @patch("core.grist_api.GristAPI.get_tables")
    def test_invalid_doc_id(self, mock_get_tables):
        from main import validate_doc_id
        from core.grist_api import GristAPI, GristAuthError

        mock_get_tables.side_effect = GristAuthError("Unauthorized")
        api = GristAPI("http://localhost:8484", "test-key")
        assert validate_doc_id(api, "bad_doc") is False


class TestCallLLM:
    """Tests pour call_llm."""

    def test_successful_llm_call(self):
        from main import call_llm
        from config import Settings

        config = {
            "formulas": [
                {"table": "T", "column": "C", "type": "Text", "formula": "@A + @B"}
            ],
            "columnChanges": [],
            "recommendations": [],
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps(config)}}]
        }

        with patch("requests.post", return_value=mock_response) as mock_post:
            settings = Settings()
            settings.VLLM_BASE_URL = "http://test:30000"
            messages = [
                {"role": "system", "content": "test"},
                {"role": "user", "content": "test"},
            ]
            result = call_llm(messages, settings, "test-model")

        assert isinstance(result, dict)
        assert "formulas" in result
        assert len(result["formulas"]) == 1

    def test_llm_retry_on_failure(self):
        from main import call_llm
        from config import Settings
        import requests

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "formulas": [], "columnChanges": [], "recommendations": []
            })}}]
        }

        with patch("requests.post", side_effect=[
            requests.exceptions.ConnectionError("network error"),
            requests.exceptions.ConnectionError("network error"),
            mock_response,
        ]) as mock_post:
            settings = Settings()
            settings.VLLM_BASE_URL = "http://test:30000"
            messages = [{"role": "user", "content": "test"}]
            result = call_llm(messages, settings, "test-model", max_retries=2)

        assert mock_post.call_count == 3  # 2 retries + 1 success

    def test_llm_invalid_json_raises(self):
        from main import call_llm
        from config import Settings

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "not json at all"}}]
        }

        with patch("requests.post", return_value=mock_response):
            settings = Settings()
            settings.VLLM_BASE_URL = "http://test:30000"
            messages = [{"role": "user", "content": "test"}]
            with pytest.raises(ValueError, match="Aucun JSON trouvé"):
                call_llm(messages, settings, "test-model")


class TestMainDryRun:
    """Tests pour le mode dry-run de main()."""

    @patch("builtins.print")
    @patch("main.select_model")
    @patch("main.GristUpdater")
    @patch("main.call_llm")
    @patch("main.SchemaAnalyzer")
    @patch("main.GristAnalyzer")
    @patch("main.validate_doc_id")
    def test_dry_run_does_not_apply(
        self, mock_validate, mock_analyzer_cls, mock_schema_cls,
        mock_call_llm, mock_updater_cls, mock_select, mock_print,
        tmp_path
    ):
        from main import main
        from config import Settings

        mock_validate.return_value = True
        mock_select.return_value = "test-model"

        # Mock GristAnalyzer
        doc_info_mock = MagicMock()
        doc_info_mock.get_table_names.return_value = ["Ventes"]
        doc_info_mock.get_table.return_value = {
            "label": "Ventes", "record_count": 10, "columns": []
        }
        mock_analyzer_cls.return_value.analyze.return_value = doc_info_mock

        # Mock SchemaAnalyzer
        mock_schema_cls.return_value.build_messages.return_value = []

        # Mock LLM
        mock_call_llm.return_value = {
            "formulas": [], "columnChanges": [], "recommendations": []
        }

        # Mock GristUpdater
        updater_instance = MagicMock()
        mock_updater_cls.return_value = updater_instance

        with patch("main.Settings") as mock_settings_cls:
            mock_settings = MagicMock()
            mock_settings.VLLM_MODEL = "test-model"
            mock_settings.GRIST_SERVER = "http://localhost:8484"
            mock_settings.GRIST_API_KEY = "test-key"
            mock_settings_cls.return_value = mock_settings

            import argparse
            args = argparse.Namespace(
                doc_id="doc123",
                request="test",
                output=str(tmp_path),
                dry_run=True,
                model=None,
            )
            with patch("sys.argv", ["main.py", "--doc-id", "doc123", "--request", "test", "--dry-run"]):
                main()

        # Vérifier que apply_config n'a PAS été appelé
        assert not updater_instance.apply_config.called
