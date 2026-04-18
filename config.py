"""Configuration du projet grist-excel."""

import os
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    """Configuration settings loaded from environment variables."""

    model_config = ConfigDict(env_file=".env", case_sensitive=False)

    # vLLM API configuration
    VLLM_BASE_URL: str = "http://172.17.0.1:30000"
    VLLM_MODEL: str = "Qwen/Qwen3.6-35B-A3B-FP8"
    VLLM_MODEL_NAME: str = ""
    VLLM_TIMEOUT: int = 300

    # Excel processing
    EXCEL_MAX_ROWS: int = 10000
    EXCEL_CHUNK_SIZE: int = 1000

    # API settings
    API_TIMEOUT: int = 30
    API_RETRIES: int = 3

    # Grist API configuration
    GRIST_API_KEY: str = ""
    GRIST_SERVER: str = "http://localhost:8484"
    GRIST_DOC_ID: str = ""

    # Grist pipeline settings
    MAX_RETRIES: int = 3
    RECORD_CHUNK_SIZE: int = 100
    TIMEOUT_GRIST: int = 30

    # Data analysis settings
    MARKITDOWN_MAX_ROWS: int = 50  # max rows per sheet in Markdown summary
    STATS_TOP_VALUES: int = 5      # top N values for categorical stats


# Global settings instance
settings = Settings()
