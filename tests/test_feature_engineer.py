from core.feature_engineer import FeaturePlan, FormulaColumn
import pytest


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
    with pytest.raises(Exception):
        FormulaColumn(table="employees", col_id="x")  # missing label, type, formula
