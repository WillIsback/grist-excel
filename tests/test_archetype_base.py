"""Tests for archetypes/base.py — BaseArchetype and GristTableResolver."""
import pytest
from unittest.mock import MagicMock, call
from archetypes.base import BaseArchetype, GristTableResolver
from core.grist_api import GristAPI


@pytest.fixture
def mock_api():
    api = MagicMock(spec=GristAPI)
    api.get_records.return_value = [
        {"id": 1, "fields": {"tableId": "Employes"}},
        {"id": 2, "fields": {"tableId": "Absences"}},
    ]
    # apply_actions returns viewId on first call (create page)
    api.apply_actions.return_value = {"retValues": [10]}
    return api


class TestGristTableResolver:
    def test_resolves_table_id_to_ref(self, mock_api):
        resolver = GristTableResolver(mock_api, "doc123")
        assert resolver.get_ref("Employes") == 1
        assert resolver.get_ref("Absences") == 2

    def test_raises_on_unknown_table(self, mock_api):
        resolver = GristTableResolver(mock_api, "doc123")
        with pytest.raises(KeyError):
            resolver.get_ref("NonExistent")

    def test_calls_grist_tables_endpoint(self, mock_api):
        GristTableResolver(mock_api, "doc123")
        mock_api.get_records.assert_called_once_with("doc123", "_grist_Tables")


class TestBaseArchetype:
    def test_is_abstract(self):
        """BaseArchetype cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseArchetype()

    def test_subclass_must_implement_apply(self):
        """Concrete subclass without apply() raises TypeError on instantiation."""
        class Incomplete(BaseArchetype):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_subclass_works(self):
        class Concrete(BaseArchetype):
            def apply(self, api, doc_id, classification, plan):
                return ["page1"]
        obj = Concrete()
        assert obj.apply(None, None, None, None) == ["page1"]

    def test_create_page_adds_view_tabbar_and_pages(self, mock_api):
        """_create_page must create _grist_Views + _grist_TabBar + _grist_Pages."""
        class Concrete(BaseArchetype):
            def apply(self, api, doc_id, classification, plan):
                return []
        obj = Concrete()
        view_id = obj._create_page(mock_api, "doc123", "My Page")
        assert view_id == 10
        # First call: _grist_Views
        first_call_actions = mock_api.apply_actions.call_args_list[0][0][1]
        assert first_call_actions[0][1] == "_grist_Views"
        assert first_call_actions[0][3]["name"] == "My Page"
        # Second call: both _grist_TabBar and _grist_Pages
        second_call_actions = mock_api.apply_actions.call_args_list[1][0][1]
        table_names = [a[1] for a in second_call_actions]
        assert "_grist_TabBar" in table_names
        assert "_grist_Pages" in table_names

    def test_add_chart_section_uses_correct_parentkey(self, mock_api):
        class Concrete(BaseArchetype):
            def apply(self, api, doc_id, classification, plan):
                return []
        obj = Concrete()
        obj._add_chart_section(mock_api, "doc123", 10, 1, "bar", "My Chart")
        actions = mock_api.apply_actions.call_args[0][1]
        fields = actions[0][3]
        assert fields["parentKey"] == "chart"
        assert fields["chartType"] == "bar"
        assert actions[0][1] == "_grist_Views_section"

    def test_add_table_section_uses_record_parentkey(self, mock_api):
        class Concrete(BaseArchetype):
            def apply(self, api, doc_id, classification, plan):
                return []
        obj = Concrete()
        obj._add_table_section(mock_api, "doc123", 10, 1)
        actions = mock_api.apply_actions.call_args[0][1]
        assert actions[0][3]["parentKey"] == "record"

    def test_add_card_list_uses_detail_parentkey(self, mock_api):
        class Concrete(BaseArchetype):
            def apply(self, api, doc_id, classification, plan):
                return []
        obj = Concrete()
        obj._add_card_list_section(mock_api, "doc123", 10, 1)
        actions = mock_api.apply_actions.call_args[0][1]
        assert actions[0][3]["parentKey"] == "detail"

    def test_add_form_uses_form_parentkey(self, mock_api):
        class Concrete(BaseArchetype):
            def apply(self, api, doc_id, classification, plan):
                return []
        obj = Concrete()
        obj._add_form_section(mock_api, "doc123", 10, 1)
        actions = mock_api.apply_actions.call_args[0][1]
        assert actions[0][3]["parentKey"] == "form"
