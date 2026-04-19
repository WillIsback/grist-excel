# tests/test_column_relevance_filter.py
from config import Settings


def test_relevance_settings_defaults():
    s = Settings()
    assert s.RELEVANCE_UPPER == 0.6
    assert s.RELEVANCE_LOWER == 0.25
    assert s.RELEVANCE_MIN_COLUMNS == 5
