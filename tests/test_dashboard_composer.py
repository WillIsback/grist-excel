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
