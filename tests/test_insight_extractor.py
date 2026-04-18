"""Tests for core/insight_extractor.py — InsightExtractor and Pydantic models."""
import json
import pytest
from pydantic import ValidationError
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightExtractor, VALID_INSIGHT_TYPES


SAMPLE_PROFILE_JSON = json.dumps({
    "sheets": ["Employes", "Absences"],
    "columns": {
        "Employes": ["ID", "Nom", "Departement", "Salaire"],
        "Absences": ["ID_Employe", "Date_Debut", "Duree_Jours"],
    },
    "stats": {
        "Employes.Departement": {"non_null": 3, "unique": 2, "top": ["IT", "RH"]},
        "Employes.Salaire": {"non_null": 3, "unique": 3, "min": 45000, "max": 75000, "avg": 60000},
        "Absences.Duree_Jours": {"non_null": 2, "unique": 2, "min": 1, "max": 3, "avg": 2},
    },
    "apparent_fk": [{"from": "Absences.ID_Employe", "to": "Employes.ID"}],
})


class TestInsightEntry:
    def test_valid_insight(self):
        from core.insight_extractor import InsightEntry
        entry = InsightEntry(
            type="distribution", table="Employes", col="Departement",
            finding="IT et RH concentrent les effectifs", priority=1,
        )
        assert entry.type == "distribution"
        assert entry.table == "Employes"

    def test_rejects_invalid_insight_type(self):
        from core.insight_extractor import InsightEntry
        with pytest.raises(ValidationError):
            InsightEntry(
                type="INVALID_TYPE", table="Employes", col="Nom",
                finding="test", priority=1,
            )


class TestInsightReport:
    def test_valid_report(self):
        data = {
            "insights": [
                {
                    "type": "distribution",
                    "table": "Employes",
                    "col": "Departement",
                    "finding": "IT et RH concentrent les effectifs",
                    "priority": 1,
                }
            ]
        }
        report = InsightReport(**data)
        assert len(report.insights) == 1
        assert report.insights[0].type == "distribution"

    def test_max_5_insights_enforced(self):
        insights = []
        for i in range(6):
            insights.append({
                "type": "distribution",
                "table": "Employes",
                "col": "Nom",
                "finding": f"insight {i}",
                "priority": i + 1,
            })
        data = {"insights": insights}
        with pytest.raises(ValidationError):
            InsightReport(**data)


class TestInsightExtractor:
    @pytest.fixture
    def mock_llm(self, monkeypatch):
        def mock_call(messages, schema=None):
            return {
                "insights": [
                    {
                        "type": "distribution",
                        "table": "Employes",
                        "col": "Departement",
                        "finding": "IT et RH concentrent 68% des effectifs",
                        "priority": 1,
                    },
                    {
                        "type": "trend",
                        "table": "Absences",
                        "col": "Date_Debut",
                        "finding": "Pic d'absences en janvier",
                        "priority": 2,
                    },
                ]
            }
        return mock_call

    def test_extract_insights(self, mock_llm, monkeypatch):
        profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
        classifier_result = ClassificationResult(
            archetype="HR", confidence=0.9,
            table_mapping={"employees": "Employes", "absences": "Absences"},
            params={"name_col": "Nom", "department_col": "Departement"},
        )
        extractor = InsightExtractor()
        monkeypatch.setattr(extractor, "_call_llm", lambda msgs, schema=None: mock_llm(msgs, schema))
        report = extractor.extract(profile, classifier_result)
        assert len(report.insights) == 2
        assert report.insights[0].type == "distribution"
        assert report.insights[0].table == "Employes"

    def test_includes_stats_in_prompt(self, mock_llm, monkeypatch):
        profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
        classifier_result = ClassificationResult(
            archetype="HR", confidence=0.9,
            table_mapping={"employees": "Employes"},
            params={"name_col": "Nom"},
        )
        extractor = InsightExtractor()
        received = []
        def capture(msgs, schema=None):
            received.extend(msgs)
            return mock_llm(msgs, schema)
        monkeypatch.setattr(extractor, "_call_llm", capture)
        extractor.extract(profile, classifier_result)
        prompt_text = " ".join(m.get("content", "") for m in received)
        assert "Salaire" in prompt_text
        assert "min" in prompt_text
