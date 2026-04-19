from core.feature_engineer import FeaturePlan, FormulaColumn
import pytest
from pydantic import ValidationError
from unittest.mock import patch, MagicMock
from core.feature_engineer import FeatureEngineer
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightEntry
from config import Settings


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


def test_apply_patches_formula_column():
    from core.grist_api import GristAPI

    eng = FeatureEngineer()
    api = MagicMock(spec=GristAPI)
    api.get_records.return_value = []

    plan = FeaturePlan(features=[
        FormulaColumn(
            table="employees",
            col_id="nb_absences",
            label="Nb Absences",
            type="Int",
            formula="len(Absences.lookupRecords(ID_Employe=$ID_Employe))",
        )
    ])
    table_mapping = {"employees": "Employes"}

    applied, failed = eng.apply(api, "doc123", plan, table_mapping)

    api.add_columns.assert_called_once_with(
        "doc123",
        "Employes",
        [{
            "id": "nb_absences",
            "fields": {
                "type": "Int",
                "label": "Nb Absences",
                "formula": "len(Absences.lookupRecords(ID_Employe=$ID_Employe))",
                "isFormula": True,
            },
        }],
    )
    assert "nb_absences" in applied
    assert failed == []


def test_apply_skips_on_api_error():
    from core.grist_api import GristAPI

    eng = FeatureEngineer()
    api = MagicMock(spec=GristAPI)
    api.add_columns.side_effect = Exception("API error")

    plan = FeaturePlan(features=[
        FormulaColumn(
            table="employees", col_id="bad_col", label="Bad", type="Text", formula="$X"
        )
    ])
    applied, failed = eng.apply(api, "doc123", plan, {"employees": "Employes"})

    assert applied == []
    assert "bad_col" in failed


def test_plan_injects_user_intent_into_prompt():
    eng = FeatureEngineer()
    captured = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured.extend(messages)
        return {"features": []}

    with patch.object(eng, "_call_llm", side_effect=fake_call_llm):
        eng.plan(_make_profile(), _make_classification(), _make_insights(),
                 user_intent="réduire le turnover")

    user_msg = captured[1]["content"]
    assert "réduire le turnover" in user_msg


def test_plan_without_intent_unchanged():
    eng = FeatureEngineer()
    captured = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured.extend(messages)
        return {"features": []}

    with patch.object(eng, "_call_llm", side_effect=fake_call_llm):
        eng.plan(_make_profile(), _make_classification(), _make_insights(),
                 user_intent=None)

    user_msg = captured[1]["content"]
    assert "Objectif" not in user_msg


def test_apply_emits_debug_payload():
    from core.grist_api import GristAPI

    eng = FeatureEngineer(Settings(DEBUG=True))
    api = MagicMock(spec=GristAPI)
    api.get_records.return_value = []
    api._doc_url.return_value = "http://localhost:8484/api/docs/doc123/tables/Employes/columns"

    plan = FeaturePlan(features=[
        FormulaColumn(
            table="employees",
            col_id="nb_absences",
            label="Nb Absences",
            type="Int",
            formula="len(Absences.lookupRecords(ID_Employe=$ID_Employe))",
        )
    ])

    with patch("core.feature_engineer.debug_print") as debug_mock:
        eng.apply(api, "doc123", plan, {"employees": "Employes"})

    debug_mock.assert_called_with(
        "FeatureEngineer.patch_columns",
        {
            "doc_id": "doc123",
            "semantic_table": "employees",
            "table_id": "Employes",
            "method": "POST",
            "url": "http://localhost:8484/api/docs/doc123/tables/Employes/columns",
            "payload": {
                "columns": [{
                    "id": "nb_absences",
                    "fields": {
                        "type": "Int",
                        "label": "Nb Absences",
                        "formula": "len(Absences.lookupRecords(ID_Employe=$ID_Employe))",
                        "isFormula": True,
                    },
                }],
            },
        },
        True,
    )
