"""Tests for core/dashboard_composer.py — DashboardComposer and Pydantic models."""
import json
import pytest
from pydantic import ValidationError
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightEntry
from core.dashboard_composer import (
    DashboardPlan,
    PageSection,
    DashboardComposer,
    WIDGET_TYPES,
    CHART_TYPES,
)
from core.visual_intents import VisualIntent, VisualIntentPlan


SAMPLE_CLASSIFICATION = ClassificationResult(
    archetype="HR", confidence=0.9,
    table_mapping={"employees": "Employes", "absences": "Absences"},
    params={"name_col": "Nom", "department_col": "Departement"},
)

SAMPLE_INSIGHTS = InsightReport(insights=[
    InsightEntry(
        type="distribution", table="Employes", col="Departement",
        finding="IT et RH concentrent 68% des effectifs", priority=1,
    ),
    InsightEntry(
        type="trend", table="Absences", col="Date_Debut",
        finding="Pic d'absences en janvier", priority=2,
    ),
])


class TestPageSection:
    def test_chart_widget(self):
        section = PageSection.model_validate({
            "widget": "chart",
            "chart_type": "bar",
            "table": "Employes",
            "x": "Departement",
            "y": "Nom",
            "agg": "count",
            "title": "Répartition par département",
        })
        assert section.widget == "chart"
        assert section.chart_type == "bar"

    def test_card_list_widget(self):
        section = PageSection.model_validate({
            "widget": "card_list",
            "table": "Employes",
            "title": "Annuaire",
        })
        assert section.widget == "card_list"

    def test_rejects_invalid_widget_type(self):
        with pytest.raises(ValidationError):
            PageSection.model_validate({"widget": "INVALID"})

    def test_rejects_invalid_chart_type(self):
        with pytest.raises(ValidationError):
            PageSection.model_validate({
                "widget": "chart", "chart_type": "INVALID",
                "table": "Employes", "x": "A", "y": "B", "agg": "count",
                "title": "test",
            })


class TestDashboardPlan:
    def test_valid_plan(self):
        data = {
            "pages": [
                {
                    "name": "Dashboard RH",
                    "sections": [
                        {"widget": "chart", "chart_type": "bar", "table": "Employes",
                         "x": "Departement", "y": "Nom", "agg": "count",
                         "title": "Répartition"},
                    ],
                }
            ]
        }
        plan = DashboardPlan(**data)
        assert len(plan.pages) == 1
        assert plan.pages[0].name == "Dashboard RH"

    def test_serializes_to_json(self):
        plan = DashboardPlan.model_validate({
            "pages": [{"name": "Test", "sections": []}]
        })
        json_str = plan.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["pages"][0]["name"] == "Test"


class TestDashboardComposer:
    @pytest.fixture
    def mock_llm_response(self):
        return {
            "pages": [
                {
                    "name": "Dashboard RH",
                    "sections": [
                        {
                            "widget": "chart", "chart_type": "bar",
                            "table": "Employes", "x": "Departement",
                            "y": "Nom", "agg": "count",
                            "title": "IT et RH concentrent 68%",
                        },
                    ],
                },
                {
                    "name": "Employés",
                    "sections": [
                        {"widget": "card_list", "table": "Employes", "title": "Annuaire"},
                    ],
                },
            ]
        }

    def test_composes_dashboard(self, mock_llm_response, monkeypatch):
        composer = DashboardComposer()
        monkeypatch.setattr(composer, "_call_llm", lambda msgs: mock_llm_response)
        plan = composer.compose(SAMPLE_CLASSIFICATION, SAMPLE_INSIGHTS)
        assert len(plan.pages) >= 1
        assert "Dashboard RH" in [p.name for p in plan.pages]

    def test_appends_summary_table_page(self, mock_llm_response, monkeypatch):
        composer = DashboardComposer()
        monkeypatch.setattr(composer, "_call_llm", lambda msgs: mock_llm_response)
        plan = composer.compose(
            SAMPLE_CLASSIFICATION,
            SAMPLE_INSIGHTS,
            summary_tables=[{
                "name": "Corr_Employes_Departement_Salaire",
                "group_by": "Departement",
                "metric": "Salaire",
                "source_table": "Employes",
            }],
        )

        assert any(page.name == "Syntheses croisees" for page in plan.pages)
        corr_page = next(page for page in plan.pages if page.name == "Syntheses croisees")
        assert corr_page.sections[0].widget == "table"
        assert corr_page.sections[0].table == "Corr_Employes_Departement_Salaire"
        assert corr_page.sections[0].title == "Croisement Departement x Salaire"

    def test_prefers_visual_intents_for_summary_sections(self, mock_llm_response, monkeypatch):
        composer = DashboardComposer()
        monkeypatch.setattr(composer, "_call_llm", lambda msgs: mock_llm_response)
        intents = VisualIntentPlan(intents=[
            VisualIntent(
                kind="cross_tab",
                source_table="Corr_Employes_Departement_Salaire",
                source_columns=["Departement", "Salaire"],
                insight_refs=[0],
                priority=0.9,
                confidence=0.8,
                presentation="summary_page",
                supported_widgets=["table"],
                premium_widgets=["advanced_chart"],
                preferred_widget="table",
                title="Croisement guide par intent",
                narrative="",
                metadata={},
            )
        ], promoted_intent_index=0, promoted_widget="advanced_chart")
        plan = composer.compose(
            SAMPLE_CLASSIFICATION,
            SAMPLE_INSIGHTS,
            summary_tables=[{
                "name": "Corr_Employes_Departement_Salaire",
                "group_by": "Departement",
                "metric": "Salaire",
                "source_table": "Employes",
            }],
            visual_intents=intents,
        )

        corr_page = next(page for page in plan.pages if page.name == "Syntheses croisees")
        assert corr_page.sections[0].title == "Croisement guide par intent"

    def test_includes_visual_intents_in_prompt(self, mock_llm_response, monkeypatch):
        composer = DashboardComposer()
        received = []

        def capture(msgs):
            received.extend(msgs)
            return mock_llm_response

        monkeypatch.setattr(composer, "_call_llm", capture)
        composer.compose(
            SAMPLE_CLASSIFICATION,
            SAMPLE_INSIGHTS,
            visual_intents=VisualIntentPlan(intents=[
                VisualIntent(
                    kind="trend",
                    source_table="Absences",
                    source_columns=["Date_Debut", "Duree_Jours"],
                    insight_refs=[1],
                    priority=0.8,
                    confidence=0.8,
                    presentation="hero_chart",
                    supported_widgets=["chart"],
                    premium_widgets=["advanced_chart"],
                    preferred_widget="chart",
                    title="Pic d'absences en janvier",
                    narrative="Pic d'absences en janvier",
                    metadata={},
                )
            ]),
        )
        prompt_text = " ".join(m.get("content", "") for m in received)
        assert "Intentions visuelles déterministes" in prompt_text
        assert "hero_chart" in prompt_text
        assert "premium=['advanced_chart']" in prompt_text
        assert "Intention premium à privilégier" in prompt_text

    def test_promoted_cross_tab_is_sorted_first(self, mock_llm_response, monkeypatch):
        composer = DashboardComposer()
        monkeypatch.setattr(composer, "_call_llm", lambda msgs: mock_llm_response)
        intents = VisualIntentPlan(
            intents=[
                VisualIntent(
                    kind="cross_tab",
                    source_table="Corr_B",
                    source_columns=["B", "Metric"],
                    insight_refs=[0],
                    priority=0.8,
                    confidence=0.8,
                    presentation="summary_page",
                    supported_widgets=["table"],
                    premium_widgets=["advanced_chart"],
                    preferred_widget="table",
                    title="Croisement B",
                    narrative="",
                    metadata={},
                ),
                VisualIntent(
                    kind="cross_tab",
                    source_table="Corr_A",
                    source_columns=["A", "Metric"],
                    insight_refs=[1],
                    priority=0.9,
                    confidence=0.9,
                    presentation="summary_page",
                    supported_widgets=["table"],
                    premium_widgets=["advanced_chart"],
                    preferred_widget="table",
                    title="Croisement A",
                    narrative="",
                    metadata={},
                ),
            ],
            promoted_intent_index=1,
            promoted_widget="advanced_chart",
        )
        plan = composer.compose(SAMPLE_CLASSIFICATION, SAMPLE_INSIGHTS, visual_intents=intents)
        corr_page = next(page for page in plan.pages if page.name == "Syntheses croisees")
        assert corr_page.sections[0].table == "Corr_A"

    def test_filters_line_chart_missing_axis(self, monkeypatch):
        composer = DashboardComposer()
        monkeypatch.setattr(composer, "_call_llm", lambda msgs: {
            "pages": [{
                "name": "Dashboard",
                "sections": [
                    {
                        "widget": "chart",
                        "chart_type": "line",
                        "table": "Absences",
                        "x": "Date_Debut",
                        "y": None,
                        "agg": "avg",
                        "title": "Courbe invalide",
                    },
                    {
                        "widget": "chart",
                        "chart_type": "bar",
                        "table": "Employes",
                        "x": "Departement",
                        "y": "Nom",
                        "agg": "count",
                        "title": "Bar valide",
                    },
                ],
            }],
        })

        plan = composer.compose(SAMPLE_CLASSIFICATION, SAMPLE_INSIGHTS)

        assert len(plan.pages) == 1
        assert len(plan.pages[0].sections) == 1
        assert plan.pages[0].sections[0].title == "Bar valide"

    def test_includes_insights_in_prompt(self, mock_llm_response, monkeypatch):
        composer = DashboardComposer()
        received = []
        def capture(msgs):
            received.extend(msgs)
            return mock_llm_response
        monkeypatch.setattr(composer, "_call_llm", capture)
        composer.compose(SAMPLE_CLASSIFICATION, SAMPLE_INSIGHTS)
        prompt_text = " ".join(m.get("content", "") for m in received)
        assert "IT et RH concentrent" in prompt_text
        assert "Pic d'absences" in prompt_text

    def test_self_reflection_pass(self):
        """Verify self-reflection keeps widgets justified by insights."""
        plan = DashboardPlan.model_validate({
            "pages": [
                {
                    "name": "Test",
                    "sections": [
                        {
                            "widget": "chart", "chart_type": "bar",
                            "table": "Employes", "x": "Departement",
                            "y": "Nom", "agg": "count",
                            "title": "IT et RH concentrent 68%",
                        },
                    ],
                }
            ]
        })
        # Self-reflection should keep this since title matches an insight finding
        validated = plan.self_reflect(SAMPLE_INSIGHTS)
        assert len(validated.pages) == 1

    def test_self_reflection_removes_unjustified_widgets(self):
        """Verify self-reflection removes widgets with no matching insight."""
        plan = DashboardPlan.model_validate({
            "pages": [
                {
                    "name": "Test",
                    "sections": [
                        {
                            "widget": "chart", "chart_type": "bar",
                            "table": "Employes", "x": "A", "y": "B", "agg": "count",
                            "title": "Some random chart not related to insights",
                        },
                    ],
                }
            ]
        })
        validated = plan.self_reflect(SAMPLE_INSIGHTS)
        # Page should be empty (all sections removed)
        assert len(validated.pages) == 0

    def test_self_reflection_keeps_non_chart_widgets(self):
        """Non-chart widgets like card_list are never removed by self-reflection."""
        plan = DashboardPlan.model_validate({
            "pages": [
                {
                    "name": "Test",
                    "sections": [
                        {"widget": "card_list", "table": "Employes", "title": "Random title"},
                    ],
                }
            ]
        })
        validated = plan.self_reflect(SAMPLE_INSIGHTS)
        assert len(validated.pages) == 1
        assert validated.pages[0].sections[0].widget == "card_list"


def test_compose_injects_user_intent_into_system_prompt():
    from unittest.mock import patch
    from core.dashboard_composer import DashboardComposer
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport, InsightEntry

    classification = ClassificationResult(
        archetype="HR", confidence=0.9,
        table_mapping={"employees": "Employes"}, params={},
    )
    insights = InsightReport(insights=[
        InsightEntry(type="distribution", table="Employes", col="Departement",
                     finding="IT domine", priority=1),
    ])
    composer = DashboardComposer()
    mock_plan = {"pages": [{"name": "RH", "sections": [
        {"widget": "chart", "title": "IT domine", "chart_type": "bar",
         "table": "Employes", "x": "Departement", "y": "Effectif", "agg": "count"}
    ]}]}
    captured = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured.extend(messages)
        return mock_plan

    with patch.object(composer, "_call_llm", side_effect=fake_call_llm):
        composer.compose(classification, insights, user_intent="analyser les coûts salariaux")

    system_msg = captured[0]["content"]
    assert "analyser les coûts salariaux" in system_msg


def test_compose_no_intent_unchanged():
    from unittest.mock import patch
    from core.dashboard_composer import DashboardComposer
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport, InsightEntry

    classification = ClassificationResult(
        archetype="HR", confidence=0.9,
        table_mapping={"employees": "Employes"}, params={},
    )
    insights = InsightReport(insights=[
        InsightEntry(type="kpi", table="Employes", col="Salaire",
                     finding="salaire moyen élevé", priority=1),
    ])
    composer = DashboardComposer()
    mock_plan = {"pages": [{"name": "RH", "sections": [
        {"widget": "chart", "title": "salaire moyen élevé", "chart_type": "bar",
         "table": "Employes", "x": "Departement", "y": "Salaire", "agg": "avg"}
    ]}]}
    captured = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured.extend(messages)
        return mock_plan

    with patch.object(composer, "_call_llm", side_effect=fake_call_llm):
        composer.compose(classification, insights, user_intent=None)

    system_msg = captured[0]["content"]
    assert "Objectif" not in system_msg
