from unittest.mock import MagicMock
from archetypes.base import BaseArchetype
from core.grist_api import GristAPI


class ConcreteArchetype(BaseArchetype):
    def apply(self, api, doc_id, classification, plan):
        return []


def _make_api(col_map):
    """Mock GristAPI: _get_col_ref_map returns col_map, apply_actions returns section_id=99."""
    api = MagicMock(spec=GristAPI)
    api.apply_actions.return_value = {"retValues": [99]}
    records = [
        {"id": ref, "fields": {"parentId": 1, "colId": col_id, "type": "Text"}}
        for col_id, ref in col_map.items()
    ]
    api.get_records.return_value = records
    return api


def test_chart_no_duplicate_field_when_x_equals_y():
    """When x and y resolve to same colRef, add field only once."""
    arch = ConcreteArchetype()
    col_map = {"SalaireBrute": 8, "Manager": 15}
    api = _make_api(col_map)

    arch._add_chart_section(api, "doc1", 1, 1, "bar", "Test", x_col="SalaireBrute", y_col="SalaireBrute")

    # Second apply_actions call adds fields
    field_call_args = api.apply_actions.call_args_list[1][0][1]
    col_refs_added = [a[3]["colRef"] for a in field_call_args]
    assert col_refs_added.count(8) == 1, f"colRef 8 added {col_refs_added.count(8)} times, expected 1"


def test_chart_fallback_adds_only_two_cols():
    """When x/y resolution fails, fallback adds at most 2 columns."""
    arch = ConcreteArchetype()
    col_map = {f"Col{i}": i for i in range(1, 8)}
    api = _make_api(col_map)

    arch._add_chart_section(api, "doc1", 1, 1, "bar", "Test", x_col=None, y_col=None)

    field_call_args = api.apply_actions.call_args_list[1][0][1]
    col_refs_added = [a[3]["colRef"] for a in field_call_args]
    assert len(col_refs_added) <= 2, f"fallback added {len(col_refs_added)} cols, expected ≤2"


def test_chart_x_and_y_different_adds_both():
    """When x and y are different valid columns, both are added in order x first."""
    arch = ConcreteArchetype()
    col_map = {"Departement": 5, "Salaire": 8}
    api = _make_api(col_map)

    arch._add_chart_section(api, "doc1", 1, 1, "bar", "Test", x_col="Departement", y_col="Salaire")

    field_call_args = api.apply_actions.call_args_list[1][0][1]
    col_refs_added = [a[3]["colRef"] for a in field_call_args]
    assert col_refs_added == [5, 8], f"expected [5, 8], got {col_refs_added}"
