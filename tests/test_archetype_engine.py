"""Tests for archetype modules."""
import pytest
import json
from unittest.mock import MagicMock
from archetypes.generic import GenericArchetype
from archetypes.hr import HRArchetype
from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan, Page, PageSection
from core.visual_intents import VisualIntent, VisualIntentPlan


@pytest.fixture
def mock_api():
    api = MagicMock(spec=GristAPI)
    api.get_records.return_value = [
        {"id": 1, "fields": {"tableId": "Employes"}},
        {"id": 2, "fields": {"tableId": "Absences"}},
    ]
    api.apply_actions.return_value = {"retValues": [10]}
    api.get_widget.return_value = None
    return api


@pytest.fixture
def classification():
    return ClassificationResult(
        archetype="GENERIC",
        confidence=0.5,
        table_mapping={"main": "Employes"},
        params={"name_col": "Nom"},
    )


@pytest.fixture
def hr_classification():
    return ClassificationResult(
        archetype="HR",
        confidence=0.91,
        table_mapping={"employees": "Employes", "absences": "Absences"},
        params={"name_col": "Nom", "department_col": "Departement"},
    )


@pytest.fixture
def simple_plan():
    return DashboardPlan(pages=[
        Page(name="Données", sections=[
            PageSection(widget="table", table="Employes", title="Tableau"),
        ]),
        Page(name="Saisie", sections=[
            PageSection(widget="form", table="Employes", title="Formulaire"),
        ]),
    ])


@pytest.fixture
def hr_plan():
    return DashboardPlan(pages=[
        Page(name="Dashboard RH", sections=[
            PageSection(
                widget="chart", chart_type="bar", table="Employes",
                x="Departement", y="Nom", agg="count",
                title="Effectifs par département",
            ),
            PageSection(
                widget="chart", chart_type="line", table="Absences",
                x="Date_Debut", y="Duree_Jours", agg="sum",
                title="Absences dans le temps",
            ),
        ]),
        Page(name="Employés", sections=[
            PageSection(widget="card_list", table="Employes", title="Annuaire"),
        ]),
        Page(name="Saisie", sections=[
            PageSection(widget="form", table="Employes", title="Nouvel employé"),
        ]),
    ])


class TestGenericArchetype:
    def test_returns_page_names(self, mock_api, classification, simple_plan):
        archetype = GenericArchetype()
        pages = archetype.apply(mock_api, "doc123", classification, simple_plan)
        assert "Données" in pages
        assert "Saisie" in pages

    def test_creates_one_view_per_plan_page(self, mock_api, classification, simple_plan):
        archetype = GenericArchetype()
        archetype.apply(mock_api, "doc123", classification, simple_plan)
        view_calls = [
            c for c in mock_api.apply_actions.call_args_list
            if "_grist_Views'" in str(c) and "AddRecord" in str(c)
            and "_grist_TabBar" not in str(c) and "_grist_Pages" not in str(c)
        ]
        assert len(view_calls) == 2

    def test_skips_section_on_missing_table(self, mock_api, simple_plan):
        """Unknown table → section skipped, page still created."""
        mock_api.get_records.return_value = []  # no tables
        archetype = GenericArchetype()
        pages = archetype.apply(mock_api, "doc123",
            ClassificationResult(archetype="GENERIC", confidence=0.4,
                                 table_mapping={}, params={}),
            simple_plan)
        assert isinstance(pages, list)
        assert len(pages) == 2  # pages created even if sections skipped

    def test_chart_section_created_with_chart_type(self, mock_api, hr_classification, hr_plan):
        archetype = GenericArchetype()
        archetype.apply(mock_api, "doc123", hr_classification, hr_plan)
        chart_calls = [
            c for c in mock_api.apply_actions.call_args_list
            if '"chart"' in str(c) or "'chart'" in str(c)
        ]
        assert len(chart_calls) >= 2

    def test_page_creation_failure_skips_that_page(self, mock_api, classification, simple_plan):
        """If _create_page raises, that page is skipped but others continue."""
        call_count = [0]
        original = mock_api.apply_actions.side_effect

        def fail_first(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Grist error")
            return {"retValues": [10]}

        mock_api.apply_actions.side_effect = fail_first
        archetype = GenericArchetype()
        pages = archetype.apply(mock_api, "doc123", classification, simple_plan)
        # First page failed, second should succeed
        assert len(pages) == 1

    def test_materializes_promoted_official_widget_for_cross_tab(self, mock_api, classification):
        mock_api.get_records.return_value = [
            {"id": 1, "fields": {"tableId": "Corr_Employes_Departement_Salaire"}},
            {"id": 11, "fields": {"parentId": 1, "colId": "Departement"}},
            {"id": 12, "fields": {"parentId": 1, "colId": "Salaire"}},
        ]
        mock_api.get_widget.return_value = {
            "widgetId": "@gristlabs/widget-chart",
            "name": "Advanced charts",
            "url": "https://gristlabs.github.io/grist-widget/chart/index.html",
            "accessLevel": "full",
        }
        plan = DashboardPlan(pages=[
            Page(name="Syntheses croisees", sections=[
                PageSection(
                    widget="table",
                    table="Corr_Employes_Departement_Salaire",
                    title="Croisement Departement x Salaire",
                ),
            ]),
        ])
        visual_intents = VisualIntentPlan(
            intents=[
                VisualIntent(
                    kind="cross_tab",
                    source_table="Corr_Employes_Departement_Salaire",
                    source_columns=["Departement", "Salaire"],
                    insight_refs=[],
                    priority=0.9,
                    confidence=0.9,
                    presentation="summary_page",
                    supported_widgets=["table"],
                    premium_widgets=["advanced_chart"],
                    preferred_widget="table",
                    title="Croisement Departement x Salaire",
                )
            ],
            promoted_intent_index=0,
            promoted_widget="advanced_chart",
        )

        archetype = GenericArchetype()
        archetype.apply(mock_api, "doc123", classification, plan, visual_intents)

        custom_calls = [
            c for c in mock_api.apply_actions.call_args_list
            if "_grist_Views_section" in str(c)
            and "custom" in str(c)
        ]
        assert custom_calls
        payload = custom_calls[0].args[1][0][3]
        options = json.loads(payload["options"])
        custom_view = json.loads(options["customView"])
        assert custom_view["widgetId"] == "@gristlabs/widget-chart"
        assert custom_view["widgetDef"]["name"] == "Advanced charts"

    def test_materializes_geo_and_markdown_widget_pages(self, mock_api, classification):
        mock_api.get_records.side_effect = [
            # GristTableResolver for map: tables
            [{"id": 1, "fields": {"tableId": "Sites"}}],
            # GristTableResolver for map: columns
            [
                {"id": 11, "fields": {"parentId": 1, "colId": "Nom"}},
                {"id": 12, "fields": {"parentId": 1, "colId": "Latitude"}},
                {"id": 13, "fields": {"parentId": 1, "colId": "Longitude"}},
            ],
            # _hide_backing_table_page: _grist_Views
            [{"id": 5, "fields": {"name": "Narrative_Summary"}}],
            # _hide_backing_table_page: _grist_Pages
            [{"id": 6, "fields": {"viewRef": 5}}],
            # _hide_backing_table_page: _grist_TabBar
            [{"id": 7, "fields": {"viewRef": 5}}],
            # fresh_resolver for markdown: tables
            [
                {"id": 1, "fields": {"tableId": "Sites"}},
                {"id": 2, "fields": {"tableId": "Narrative_Summary"}},
            ],
            # fresh_resolver for markdown: columns
            [{"id": 21, "fields": {"parentId": 2, "colId": "Content"}}],
        ]
        mock_api.get_widget.side_effect = [
            {
                "widgetId": "@gristlabs/widget-map#map",
                "name": "Map",
                "url": "https://gristlabs.github.io/grist-widget/map/index.html",
                "accessLevel": "read table",
            },
            {
                "widgetId": "@gristlabs/widget-markdown",
                "name": "Markdown",
                "url": "https://gristlabs.github.io/grist-widget/markdown",
                "accessLevel": "full",
            },
        ]
        plan = DashboardPlan(pages=[])
        visual_intents = VisualIntentPlan(
            intents=[
                VisualIntent(
                    kind="geo",
                    source_table="Sites",
                    source_columns=["Nom", "Latitude", "Longitude"],
                    insight_refs=[],
                    priority=0.7,
                    confidence=0.8,
                    presentation="geo_page",
                    supported_widgets=[],
                    premium_widgets=["map"],
                    preferred_widget="map",
                    title="Carte Sites",
                    metadata={
                        "columns_mapping": {
                            "Name": "Nom",
                            "Latitude": "Latitude",
                            "Longitude": "Longitude",
                        },
                        "access": "read table",
                    },
                ),
                VisualIntent(
                    kind="narrative",
                    source_table="Sites",
                    source_columns=["Nom"],
                    insight_refs=[],
                    priority=0.6,
                    confidence=0.7,
                    presentation="narrative_block",
                    supported_widgets=[],
                    premium_widgets=["markdown"],
                    preferred_widget="markdown",
                    title="Resume analytique",
                    narrative="# Resume analytique\n\n- Test",
                    metadata={"table_name": "Narrative_Summary", "content_column": "Content"},
                ),
            ]
        )

        archetype = GenericArchetype()
        pages = archetype.apply(mock_api, "doc123", classification, plan, visual_intents)

        assert "Carte Sites" in pages
        assert "Resume analytique" in pages
        mock_api.create_table.assert_called_once_with(
            "doc123",
            "Narrative_Summary",
            columns=[{"id": "Content", "fields": {"type": "Text"}}],
        )
        mock_api.add_records.assert_called_once_with(
            "doc123",
            "Narrative_Summary",
            [{"Content": "# Resume analytique\n\n- Test"}],
        )

        custom_section_calls = [
            c for c in mock_api.apply_actions.call_args_list
            if "_grist_Views_section" in str(c) and "custom" in str(c)
        ]
        assert len(custom_section_calls) == 2
        geo_payload = custom_section_calls[0].args[1][0][3]
        geo_options = json.loads(geo_payload["options"])
        geo_custom_view = json.loads(geo_options["customView"])
        assert geo_custom_view["widgetId"] == "@gristlabs/widget-map#map"
        assert geo_custom_view["columnsMapping"]["Name"] == 11
        assert geo_custom_view["columnsMapping"]["Latitude"] == 12
        assert geo_custom_view["columnsMapping"]["Longitude"] == 13
        assert geo_custom_view["access"] == "read table"

        markdown_payload = custom_section_calls[1].args[1][0][3]
        markdown_options = json.loads(markdown_payload["options"])
        markdown_custom_view = json.loads(markdown_options["customView"])
        assert markdown_custom_view["widgetId"] == "@gristlabs/widget-markdown"
        assert markdown_custom_view["columnsMapping"] == {"Content": 21}
        assert markdown_custom_view["access"] == "full"


class TestHRArchetype:
    def test_is_subclass_of_generic(self):
        assert issubclass(HRArchetype, GenericArchetype)

    def test_apply_returns_all_page_names(self, mock_api, hr_classification, hr_plan):
        archetype = HRArchetype()
        pages = archetype.apply(mock_api, "doc123", hr_classification, hr_plan)
        assert "Dashboard RH" in pages
        assert "Employés" in pages
        assert "Saisie" in pages

    def test_missing_absences_table_skips_gracefully(self, hr_classification, hr_plan):
        api = MagicMock(spec=GristAPI)
        api.get_records.return_value = [
            {"id": 1, "fields": {"tableId": "Employes"}},
        ]
        api.apply_actions.return_value = {"retValues": [10]}
        archetype = HRArchetype()
        pages = archetype.apply(api, "doc123", hr_classification, hr_plan)
        assert isinstance(pages, list)
        assert len(pages) > 0


from core.archetype_engine import ArchetypeEngine
from archetypes.decisionnel import DecisionnelArchetype
from archetypes.support import SupportArchetype
from archetypes.student import StudentArchetype
from archetypes.si import SIArchetype
from archetypes.project import ProjectArchetype
from unittest.mock import patch


class TestArchetypeEngine:
    def test_dispatches_hr_to_hr_archetype(self, mock_api, hr_classification, hr_plan):
        engine = ArchetypeEngine(mock_api)
        with patch.object(HRArchetype, "apply", return_value=["p1"]) as mock_apply:
            result = engine.apply("doc123", hr_classification, hr_plan)
        mock_apply.assert_called_once()
        assert result == ["p1"]

    def test_dispatches_generic_archetype(self, mock_api, classification, simple_plan):
        engine = ArchetypeEngine(mock_api)
        with patch.object(GenericArchetype, "apply", return_value=["p1"]) as mock_apply:
            result = engine.apply("doc123", classification, simple_plan)
        mock_apply.assert_called_once()
        assert result == ["p1"]

    def test_passes_visual_intents_to_archetype(self, mock_api, classification, simple_plan):
        engine = ArchetypeEngine(mock_api)
        visual_intents = VisualIntentPlan(intents=[])
        with patch.object(GenericArchetype, "apply", return_value=["p1"]) as mock_apply:
            engine.apply("doc123", classification, simple_plan, visual_intents)

        assert mock_apply.call_args.args[-1] is visual_intents

    def test_falls_back_to_generic_on_unknown_archetype(self, mock_api, simple_plan):
        """Unknown archetype string → GenericArchetype used."""
        classification = ClassificationResult(
            archetype="GENERIC", confidence=0.3,
            table_mapping={}, params={},
        )
        engine = ArchetypeEngine(mock_api)
        # confidence < 0.6 forces GENERIC anyway; also test explicit unknown via mock
        with patch.dict("core.archetype_engine.ARCHETYPE_MAP", {}, clear=True):
            with patch.object(GenericArchetype, "apply", return_value=[]) as mock_apply:
                engine.apply("doc123", classification, simple_plan)
        mock_apply.assert_called_once()

    def test_returns_empty_list_on_exception(self, mock_api, hr_classification, hr_plan):
        engine = ArchetypeEngine(mock_api)
        with patch.object(HRArchetype, "apply", side_effect=Exception("boom")):
            result = engine.apply("doc123", hr_classification, hr_plan)
        assert result == []

    def test_all_seven_archetypes_in_map(self):
        from core.archetype_engine import ARCHETYPE_MAP
        expected = {"HR", "DECISIONNEL", "SUPPORT", "STUDENT", "SI", "PROJECT", "GENERIC"}
        assert set(ARCHETYPE_MAP.keys()) == expected
