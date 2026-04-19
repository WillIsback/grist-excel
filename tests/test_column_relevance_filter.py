# tests/test_column_relevance_filter.py
from config import Settings


def test_relevance_settings_defaults():
    s = Settings()
    assert s.RELEVANCE_UPPER == 0.6
    assert s.RELEVANCE_LOWER == 0.25
    assert s.RELEVANCE_MIN_COLUMNS == 5


import dataclasses
from unittest.mock import patch
from core.column_relevance_filter import ColumnRelevanceFilter
from core.data_analyzer import DataProfile
from config import Settings


def _make_profile():
    return DataProfile(
        sheets=["Employés", "Absences"],
        columns={
            "Employés": ["Département", "Salaire", "Nom", "ID"],
            "Absences": ["Date", "Durée"],
        },
        stats={
            "Employés.Département": {"non_null": 45, "top": ["IT", "RH"]},
            "Employés.Salaire": {"non_null": 45, "min": 30000.0, "max": 95000.0, "avg": 57000.0},
            "Employés.Nom": {"non_null": 45, "top": ["Martin"]},
            "Employés.ID": {"non_null": 45, "unique": 45},
            "Absences.Date": {"non_null": 100, "top": ["2024-07"]},
            "Absences.Durée": {"non_null": 100, "min": 1.0, "max": 30.0, "avg": 5.0},
        },
        apparent_fk=[],
        markdown_summary="",
    )


def test_empty_intent_returns_original_profile():
    fltr = ColumnRelevanceFilter()
    profile = _make_profile()
    result = fltr.filter(profile, "")
    assert result is profile


def test_whitespace_intent_returns_original_profile():
    fltr = ColumnRelevanceFilter()
    profile = _make_profile()
    result = fltr.filter(profile, "   ")
    assert result is profile


def test_hard_in_columns_always_included():
    fltr = ColumnRelevanceFilter()
    scores = {
        "Employés.Département": 0.9,
        "Employés.Salaire": 0.8,
        "Employés.Nom": 0.1,
        "Employés.ID": 0.05,
        "Absences.Date": 0.1,
        "Absences.Durée": 0.1,
    }
    included = fltr._apply_hysteresis(scores)
    assert "Employés.Département" in included
    assert "Employés.Salaire" in included


def test_hard_out_columns_excluded():
    fltr = ColumnRelevanceFilter()
    scores = {
        "Employés.Département": 0.9,   # hard-in
        "Employés.Nom": 0.1,            # hard-out
        "Absences.Date": 0.1,           # hard-out, no same-table hard-in
    }
    included = fltr._apply_hysteresis(scores)
    assert "Absences.Date" not in included
    assert "Employés.Nom" not in included


def test_soft_zone_included_if_same_table_as_hard_in():
    fltr = ColumnRelevanceFilter()
    scores = {
        "Employés.Département": 0.9,   # hard-in
        "Employés.Salaire": 0.4,        # soft zone, same table → include
        "Absences.Date": 0.4,           # soft zone, no hard-in same table
    }
    included = fltr._apply_hysteresis(scores)
    assert "Employés.Salaire" in included


def test_floor_ensures_minimum_columns():
    s = Settings(RELEVANCE_MIN_COLUMNS=3, RELEVANCE_UPPER=0.6, RELEVANCE_LOWER=0.25)
    fltr = ColumnRelevanceFilter(s)
    scores = {
        "A.col1": 0.9,   # hard-in
        "B.col2": 0.4,   # soft, no solidarity
        "C.col3": 0.35,  # soft, no solidarity
    }
    included = fltr._apply_hysteresis(scores)
    assert len(included) >= 3


def test_filter_trims_stats_only():
    fltr = ColumnRelevanceFilter()
    profile = _make_profile()
    scores = {k: 0.9 for k in ["Employés.Département", "Employés.Salaire"]}
    scores.update({k: 0.1 for k in ["Employés.Nom", "Employés.ID", "Absences.Date", "Absences.Durée"]})

    with patch.object(fltr, "_score_columns", return_value=scores):
        result = fltr.filter(profile, "analyse des salaires par département")

    assert result.columns == profile.columns
    assert result.sheets == profile.sheets
    assert result.apparent_fk == profile.apparent_fk
    assert "Employés.Département" in result.stats
    assert "Employés.Salaire" in result.stats


def test_filter_falls_back_on_too_few_columns():
    s = Settings(RELEVANCE_MIN_COLUMNS=10)  # impossible to satisfy with 6 columns
    fltr = ColumnRelevanceFilter(s)
    profile = _make_profile()
    all_low = {k: 0.1 for k in profile.stats}

    with patch.object(fltr, "_score_columns", return_value=all_low):
        result = fltr.filter(profile, "intent")

    assert result is profile  # fell back to full profile
