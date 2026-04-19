from core.feature_engineer import FeaturePlan, FormulaColumn
import pytest
from pydantic import ValidationError
from unittest.mock import patch, MagicMock
from core.feature_engineer import FeatureEngineer
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightEntry


def _make_profile():
    p = DataProfile.__new__(DataProfile)
    p.sheets = ["Employés"]
    p.columns = {"Employés": ["ID_Employe", "Salaire_Brute", "Manager"]}
    p.apparent_fk = []
    p.stats = {}
    return p


def _make_classification():
    return ClassificationResult(
        archetype="HR",
        confidence=0.95,
        table_mapping={"employees": "Employés"},
        params={},
    )


def _make_insights():
    return InsightReport(insights=[
        InsightEntry(type="outlier", table="Employés", col="Manager",
                     finding="6 null managers", priority=1),
    ])


def test_feature_engineer_plan_calls_llm():
    eng = FeatureEngineer()
    mock_response = {
        "features": [{
            "table": "employees",
            "col_id": "sans_manager",
            "label": "Sans Manager",
            "type": "Toggle",
            "formula": "not bool($Manager)",
        }]
    }
    with patch.object(eng, "_call_llm", return_value=mock_response) as mock_llm:
        plan = eng.plan(_make_profile(), _make_classification(), _make_insights())
    mock_llm.assert_called_once()
    assert len(plan.features) == 1
    assert plan.features[0].col_id == "sans_manager"


def test_feature_plan_valid():
    plan = FeaturePlan(features=[
        FormulaColumn(
            table="employees",
            col_id="nb_absences",
            label="Nb Absences",
            type="Int",
            formula="len(Absences.lookupRecords(ID_Employe=$ID_Employe))",
        )
    ])
    assert len(plan.features) == 1
    assert plan.features[0].col_id == "nb_absences"


def test_feature_plan_empty():
    plan = FeaturePlan(features=[])
    assert plan.features == []


def test_formula_column_requires_all_fields():
    with pytest.raises(ValidationError):
        FormulaColumn(table="employees", col_id="x")  # missing label, type, formula
