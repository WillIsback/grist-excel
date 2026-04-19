"""Tests for deterministic visual intent resolution."""

from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightEntry, InsightReport
from core.visual_intents import VisualIntentResolver


def _profile() -> DataProfile:
    return DataProfile(
        sheets=["Employes", "Absences", "Sites"],
        columns={
            "Employes": ["ID", "Departement", "Salaire"],
            "Absences": ["Date_Debut", "Duree_Jours"],
            "Sites": ["Nom", "Latitude", "Longitude"],
        },
        stats={
            "Employes.Salaire": {"avg": 10, "min": 1, "max": 20},
            "Absences.Duree_Jours": {"avg": 2, "min": 1, "max": 5},
            "Sites.Latitude": {"avg": 48.0, "min": 47.5, "max": 48.5},
            "Sites.Longitude": {"avg": 2.0, "min": 1.5, "max": 2.5},
            "Sites.Nom": {"non_null": 2, "null": 0, "unique": 2, "top": ["Paris", "Lyon"]},
        },
        apparent_fk=[],
        markdown_summary="# Test",
        summary_tables=[{
            "name": "Corr_Employes_Departement_Salaire",
            "group_by": "Departement",
            "metric": "Salaire",
            "source_table": "Employes",
            "columns": [],
            "records": [],
        }],
    )


def _classification() -> ClassificationResult:
    return ClassificationResult(
        archetype="GENERIC",
        confidence=0.9,
        table_mapping={"main": "Employes", "events": "Absences"},
        params={},
    )


def _insights() -> InsightReport:
    return InsightReport(insights=[
        InsightEntry(
            type="relation",
            table="Employes",
            col="Departement",
            finding="Des écarts de salaire apparaissent par département",
            priority=1,
        ),
        InsightEntry(
            type="trend",
            table="Absences",
            col="Date_Debut",
            finding="Les absences montent en janvier",
            priority=2,
        ),
    ])


def test_resolver_builds_cross_tab_trend_and_narrative_intents():
    plan = VisualIntentResolver().resolve(_profile(), _classification(), _insights())

    kinds = [intent.kind for intent in plan.intents]
    assert "cross_tab" in kinds
    assert "trend" in kinds
    assert "geo" in kinds
    assert "narrative" in kinds
    assert "entity_detail" in kinds


def test_resolver_promotes_single_premium_intent():
    plan = VisualIntentResolver().resolve(_profile(), _classification(), _insights())

    assert plan.promoted_intent_index is not None
    assert plan.promoted_widget == "advanced_chart"
    promoted = plan.get_promoted_intent()
    assert promoted is not None
    assert promoted.kind in {"trend", "cross_tab"}


def test_cross_tab_intent_uses_summary_table_name():
    plan = VisualIntentResolver().resolve(_profile(), _classification(), _insights())
    cross_tab = next(intent for intent in plan.intents if intent.kind == "cross_tab")

    assert cross_tab.source_table == "Corr_Employes_Departement_Salaire"
    assert cross_tab.presentation == "summary_page"
    assert cross_tab.supported_widgets == ["table"]
    assert cross_tab.premium_widgets == ["advanced_chart"]
    assert cross_tab.preferred_widget == "table"


def test_geo_intent_detects_lat_lon_table():
    plan = VisualIntentResolver().resolve(_profile(), _classification(), _insights())
    geo = next(intent for intent in plan.intents if intent.kind == "geo")

    assert geo.source_table == "Sites"
    assert geo.preferred_widget == "map"
    assert geo.metadata["columns_mapping"]["Name"] == "Nom"
    assert geo.metadata["columns_mapping"]["Latitude"] == "Latitude"
    assert geo.metadata["columns_mapping"]["Longitude"] == "Longitude"


def test_narrative_intent_builds_markdown_content():
    plan = VisualIntentResolver().resolve(_profile(), _classification(), _insights())
    narrative = next(intent for intent in plan.intents if intent.kind == "narrative")

    assert narrative.preferred_widget == "markdown"
    assert narrative.narrative is not None
    assert narrative.narrative.startswith("# R")
    assert "Des écarts de salaire apparaissent par département" in narrative.narrative