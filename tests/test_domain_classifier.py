"""Tests for core/domain_classifier.py — DomainClassifier and Pydantic models."""
import json
import pytest
from pydantic import ValidationError
from core.data_analyzer import DataProfile
from core.domain_classifier import (
    ClassificationResult,
    DomainClassifier,
    ARCHETYPE_CHOICES,
)


SAMPLE_PROFILE_JSON = json.dumps({
    "sheets": ["Employes", "Absences"],
    "columns": {
        "Employes": ["ID", "Nom", "Departement", "Salaire"],
        "Absences": ["ID_Employe", "Date_Debut", "Duree_Jours"],
    },
    "stats": {
        "Employes.Departement": {"non_null": 3, "unique": 2, "top": ["IT", "RH"]},
        "Employes.Salaire": {"non_null": 3, "unique": 3, "min": 45000, "max": 75000, "avg": 60000},
    },
    "apparent_fk": [{"from": "Absences.ID_Employe", "to": "Employes.ID"}],
})


class TestClassificationResult:
    def test_valid_hr_classification(self):
        data = {
            "archetype": "HR",
            "confidence": 0.91,
            "table_mapping": {"employees": "Employes", "absences": "Absences"},
            "params": {"name_col": "Nom", "department_col": "Departement"},
        }
        result = ClassificationResult(**data)
        assert result.archetype == "HR"
        assert result.confidence == 0.91

    def test_rejects_invalid_archetype(self):
        data = {
            "archetype": "INVALID_TYPE",
            "confidence": 0.5,
            "table_mapping": {},
            "params": {},
        }
        with pytest.raises(ValidationError):
            ClassificationResult(**data)

    def test_defaults_generic_when_confidence_low(self):
        data = {
            "archetype": "HR",
            "confidence": 0.3,
            "table_mapping": {"employees": "Employes"},
            "params": {},
        }
        result = ClassificationResult(**data)
        assert result.archetype == "GENERIC"

    def test_serializes_to_json(self):
        data = {
            "archetype": "HR",
            "confidence": 0.85,
            "table_mapping": {"employees": "Employes"},
            "params": {"name_col": "Nom"},
        }
        result = ClassificationResult(**data)
        json_str = result.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["archetype"] == "HR"


class TestDomainClassifier:
    @pytest.fixture
    def mock_llm(self, monkeypatch):
        """Provide a mock LLM that returns controlled JSON dict."""
        def mock_call(messages, guided_schema=None):
            return {
                "archetype": "HR",
                "confidence": 0.91,
                "table_mapping": {"employees": "Employes", "absences": "Absences"},
                "params": {"name_col": "Nom", "department_col": "Departement"},
            }
        return mock_call

    def test_classifies_hr_data(self, mock_llm, monkeypatch):
        profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
        classifier = DomainClassifier()
        monkeypatch.setattr(classifier, "_call_llm", lambda msgs, schema=None: mock_llm(msgs, schema))
        result = classifier.classify(profile)
        assert result.archetype == "HR"
        assert "Employes" in result.table_mapping.values()

    def test_builds_prompt_with_sheets_and_columns(self, mock_llm, monkeypatch):
        profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
        classifier = DomainClassifier()
        received_messages = []
        def capture(msgs, schema=None):
            received_messages.extend(msgs)
            return mock_llm(msgs, schema)
        monkeypatch.setattr(classifier, "_call_llm", capture)
        classifier.classify(profile)
        prompt_text = " ".join(m.get("content", "") for m in received_messages)
        assert "Employes" in prompt_text
        assert "Absences" in prompt_text
        assert "ID" in prompt_text
        assert "Nom" in prompt_text
