"""Tests for model discovery module - TDD approach."""
import pytest
import requests
from unittest.mock import Mock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Settings
from core.model_discovery import list_available_models, select_model


class TestListAvailableModels:
    """Tests for list_available_models function."""

    def test_list_available_models_success(self):
        """Test successful listing of available models from vLLM API."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [{"id": "model1"}, {"id": "model2"}]
        }
        mock_response.raise_for_status = Mock()

        settings = Settings()
        settings.VLLM_BASE_URL = "http://localhost:30000"

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = list_available_models(settings)

        mock_get.assert_called_once_with(
            "http://localhost:30000/v1/models",
            timeout=settings.VLLM_TIMEOUT
        )
        assert result == ["model1", "model2"]

    def test_list_available_models_empty(self):
        """Test listing when vLLM returns empty data array."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = Mock()

        settings = Settings()
        settings.VLLM_BASE_URL = "http://localhost:30000"

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = list_available_models(settings)

        assert result == []

    def test_list_available_models_no_data_key(self):
        """Test listing when vLLM response has no 'data' key."""
        mock_response = Mock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status = Mock()

        settings = Settings()
        settings.VLLM_BASE_URL = "http://localhost:30000"

        with patch("requests.get", return_value=mock_response) as mock_get:
            result = list_available_models(settings)

        assert result == []

    def test_list_available_models_http_error(self):
        """Test that HTTP errors are propagated."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "404 Client Error"
        )

        settings = Settings()
        settings.VLLM_BASE_URL = "http://localhost:30000"

        with patch("requests.get", return_value=mock_response):
            result = list_available_models(settings)
            assert result == []


class TestSelectModel:
    """Tests for select_model function."""

    @pytest.fixture
    def settings(self):
        """Provide test settings."""
        s = Settings()
        s.VLLM_BASE_URL = "http://localhost:30000"
        s.VLLM_MODEL = "Qwen3.5-122B"
        return s

    def test_select_model_explicit_name_available(self, settings):
        """Test selecting an explicit model that is available."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=["m1", "m2"]
        ):
            result = select_model(settings, model_name="m1")

        assert result == "m1"

    def test_select_model_explicit_name_unavailable(self, settings):
        """Test that selecting an unavailable model raises ValueError."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=["m1", "m2"]
        ):
            with pytest.raises(ValueError, match="Model 'm3' not available"):
                select_model(settings, model_name="m3")

    def test_select_model_empty_list_fallback(self, settings):
        """Test fallback to settings.VLLM_MODEL when no models available."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=[]
        ):
            result = select_model(settings)

        assert result == "Qwen3.5-122B"

    def test_select_model_first_available(self, settings):
        """Test that first available model is selected when no explicit name."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=["model-a", "model-b"]
        ):
            result = select_model(settings)

        assert result == "model-a"

    def test_select_model_interactive_by_index(self, settings, monkeypatch):
        """Test interactive selection by numeric index."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=["m1", "m2", "m3"]
        ):
            monkeypatch.setattr("builtins.input", lambda prompt: "2")
            result = select_model(settings, interactive=True)

        assert result == "m2"

    def test_select_model_interactive_by_name(self, settings, monkeypatch):
        """Test interactive selection by model name."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=["m1", "m2"]
        ):
            monkeypatch.setattr("builtins.input", lambda prompt: "m2")
            result = select_model(settings, interactive=True)

        assert result == "m2"

    def test_select_model_interactive_invalid_index(self, settings, monkeypatch):
        """Test interactive selection with out-of-bounds index raises ValueError."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=["m1"]
        ):
            monkeypatch.setattr("builtins.input", lambda prompt: "5")
            with pytest.raises(ValueError, match="Choix invalide : 5"):
                select_model(settings, interactive=True)

    def test_select_model_interactive_invalid_name(self, settings, monkeypatch):
        """Test interactive selection with unknown model name raises ValueError."""
        with patch(
            "core.model_discovery.list_available_models",
            return_value=["m1"]
        ):
            monkeypatch.setattr("builtins.input", lambda prompt: "unknown")
            with pytest.raises(ValueError, match="Choix invalide : unknown"):
                select_model(settings, interactive=True)
