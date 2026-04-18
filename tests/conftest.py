"""Pytest fixtures for grist-excel tests."""
import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_vllm_response():
    """Mock response for vLLM API calls."""
    return {
        "id": "test-completion",
        "object": "text_completion",
        "created": 1234567890,
        "model": "Qwen3.5-122B",
        "choices": [
            {
                "text": "This is a test response from the model.",
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25
        }
    }


@pytest.fixture
def mock_requests_get(mock_vllm_response):
    """Mock requests.get for vLLM API calls."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_vllm_response
    return mock_response


@pytest.fixture
def mock_requests_post(mock_vllm_response):
    """Mock requests.post for vLLM API calls."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_vllm_response
    return mock_response


@pytest.fixture
def config_settings():
    """Provide test configuration settings."""
    from config import settings
    return settings


@pytest.fixture
def mock_config(monkeypatch):
    """Mock configuration for testing."""
    monkeypatch.setenv("VLLM_BASE_URL", "http://test:30000")
    monkeypatch.setenv("VLLM_MODEL", "test-model")
    from config import Settings
    return Settings()
