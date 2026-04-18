# Data-to-Dashboard — Plan B: Multi-Agent LLM Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three LLM-driven agents (Domain Classifier, Insight Extractor, Dashboard Composer) that transform a DataProfile into a DashboardPlan ready for the Archetype Engine.

**Architecture:** Three independent modules with Pydantic models for vLLM `guided_json`, plus a `PipelineOrchestrator` that chains them together. Each agent takes the previous agent's output as input and uses structured JSON output constrained by Pydantic schemas. No free-text generation — all values come from the DataProfile lists.

**Tech Stack:** Python 3.11, Pydantic v2 (BaseModel, Field, Literal), requests (vLLM HTTP), pytest, unittest.mock

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `core/data_analyzer.py` | Add `to_json()` method to `DataProfile` |
| Create | `core/domain_classifier.py` | Agent 2: DataProfile → ClassificationResult (Pydantic + guided_json) |
| Create | `core/insight_extractor.py` | Agent 3: DataProfile + ClassificationResult → InsightReport |
| Create | `core/dashboard_composer.py` | Agent 4: ClassificationResult + InsightReport → DashboardPlan |
| Create | `core/pipeline.py` | PipelineOrchestrator: chains Agent 1 → 2 → 3 → 4 |
| Modify | `requirements.txt` | Add `openai` (for vLLM guided_json compatibility) |
| Create | `tests/test_domain_classifier.py` | Tests for DomainClassifier |
| Create | `tests/test_insight_extractor.py` | Tests for InsightExtractor |
| Create | `tests/test_dashboard_composer.py` | Tests for DashboardComposer |
| Create | `tests/test_pipeline.py` | Tests for PipelineOrchestrator |

---

### Task 1: DataProfile.to_json()

**Files:**
- Modify: `core/data_analyzer.py`
- Test: `tests/test_data_analyzer.py`

- [ ] **Step 1: Add test for to_json()**

Append to `tests/test_data_analyzer.py`:

```python
    def test_to_json_returns_valid_json(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        json_str = profile.to_json()
        parsed = json.loads(json_str)
        assert "sheets" in parsed
        assert "columns" in parsed
        assert "stats" in parsed
        assert "apparent_fk" in parsed
        assert "Employes" in parsed["sheets"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_data_analyzer.py::TestDataProfile::test_to_json_returns_valid_json -v`
Expected: `AttributeError: 'DataProfile' object has no attribute 'to_json'`

- [ ] **Step 3: Add to_json() method to DataProfile**

Append to the `DataProfile` class in `core/data_analyzer.py`, after the `as_prompt_context()` method:

```python
    def to_json(self) -> str:
        """Serialize the profile to JSON for LLM guided_json consumption."""
        return json.dumps(
            {
                "sheets": self.sheets,
                "columns": self.columns,
                "stats": self.stats,
                "apparent_fk": self.apparent_fk,
            },
            ensure_ascii=False,
            indent=2,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_data_analyzer.py::TestDataProfile::test_to_json_returns_valid_json -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/data_analyzer.py tests/test_data_analyzer.py
git commit -m "feat: add DataProfile.to_json() for LLM agent pipeline"
```

---

### Task 2: DomainClassifier Pydantic Models

**Files:**
- Create: `core/domain_classifier.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_domain_classifier.py`:

```python
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
        """Provide a mock LLM that returns controlled JSON."""
        def mock_call(messages, guided_schema=None):
            return json.dumps({
                "archetype": "HR",
                "confidence": 0.91,
                "table_mapping": {"employees": "Employes", "absences": "Absences"},
                "params": {"name_col": "Nom", "department_col": "Departement"},
            })
        return mock_call

    def test_classifies_hr_data(self, mock_llm, monkeypatch):
        profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
        classifier = DomainClassifier()
        monkeypatch.setattr(classifier, "_call_llm", lambda msgs, schema: mock_llm(msgs, schema))
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_domain_classifier.py -v 2>&1 | head -15`
Expected: `ModuleNotFoundError: No module named 'core.domain_classifier'`

- [ ] **Step 3: Implement `core/domain_classifier.py`**

Create `core/domain_classifier.py`:

```python
"""Agent 2 — Domain Classifier.

Takes a DataProfile and classifies the business domain using vLLM guided_json.
All output values are constrained to the lists provided in the DataProfile.

Outputs: ClassificationResult (archetype, confidence, table_mapping, params)
"""

from __future__ import annotations

import json
import requests
from typing import Any
from pydantic import BaseModel, Field, field_validator

from config import Settings
from core.data_analyzer import DataProfile


ARCHETYPE_CHOICES = [
    "HR",
    "DECISIONNEL",
    "SUPPORT",
    "STUDENT",
    "SI",
    "PROJECT",
    "GENERIC",
]


class ClassificationResult(BaseModel):
    """Output schema for the Domain Classifier agent."""

    archetype: str = Field(
        description="Business domain archetype. Must be one of: " + ", ".join(ARCHETYPE_CHOICES)
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score between 0.0 and 1.0"
    )
    table_mapping: dict[str, str] = Field(
        description="Maps semantic role names to actual sheet/table names from the data. "
                    "Keys are semantic roles (e.g. 'employees', 'absences'). "
                    "Values must be exact sheet names from the input data."
    )
    params: dict[str, str] = Field(
        description="Maps semantic parameter names to actual column names from the data. "
                    "Keys are parameter names (e.g. 'name_col', 'department_col'). "
                    "Values must be exact column names from the input data."
    )

    @field_validator("archetype")
    @classmethod
    def validate_archetype(cls, v: str) -> str:
        if v not in ARCHETYPE_CHOICES:
            raise ValueError(f"archetype must be one of {ARCHETYPE_CHOICES}, got '{v}'")
        return v

    def enforce_low_confidence_generic(self) -> "ClassificationResult":
        """Force GENERIC archetype when confidence < 0.6."""
        if self.confidence < 0.6:
            self.archetype = "GENERIC"
        return self


class DomainClassifier:
    """Classifies a DataProfile into a business domain archetype."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def classify(self, profile: DataProfile) -> ClassificationResult:
        """Classify the data profile into a business domain.

        Args:
            profile: DataProfile from Agent 1

        Returns:
            ClassificationResult with archetype, confidence, mappings
        """
        prompt = self._build_prompt(profile)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un classificateur de domaine métier. "
                    "Analysez le profil de données et identifiez le domaine métier. "
                    "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé. "
                    "Ne générez jamais de valeurs libres — utilisez uniquement "
                    "les noms de feuilles et colonnes fournis dans les données."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        result = ClassificationResult(**self._call_llm(messages))
        return result.enforce_low_confidence_generic()

    def _build_prompt(self, profile: DataProfile) -> str:
        """Build the classification prompt from the DataProfile."""
        sheets = profile.sheets
        columns = profile.columns
        fk = profile.apparent_fk

        prompt_lines = [
            "Classez ce jeu de données dans un domaine métier.",
            "",
            "Feuilles disponibles :",
        ]
        for sheet in sheets:
            cols = columns.get(sheet, [])
            prompt_lines.append(f"  - {sheet}: {', '.join(cols)}")

        prompt_lines.extend([
            "",
            "Relations détectées :",
        ])
        if fk:
            for relation in fk:
                prompt_lines.append(f"  - {relation['from']} → {relation['to']}")
        else:
            prompt_lines.append("  (aucune)")

        prompt_lines.extend([
            "",
            "Schéma JSON attendu :",
            json.dumps(ClassificationResult.model_json_schema(), ensure_ascii=False, indent=2),
            "",
            "IMPORTANT: Les valeurs de 'table_mapping' doivent être EXACTEMENT les noms de feuilles ci-dessus. "
            "Les valeurs de 'params' doivent être EXACTEMENT les noms de colonnes ci-dessus.",
        ])

        return "\n".join(prompt_lines)

    def _call_llm(self, messages: list[dict]) -> dict[str, Any]:
        """Call vLLM with guided_json schema.

        Override this method in tests or for alternative LLM backends.
        """
        url = f"{self.settings.VLLM_BASE_URL}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3,
            "extra_body": {
                "guided_json": ClassificationResult.model_json_schema(),
            },
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
```

Also add a `from_json` class method to `DataProfile` in `core/data_analyzer.py`, right after the `to_json()` method:

```python
    @classmethod
    def from_json(cls, json_str: str) -> "DataProfile":
        """Deserialize a DataProfile from JSON string."""
        data = json.loads(json_str)
        return cls(
            sheets=data["sheets"],
            columns=data["columns"],
            stats=data["stats"],
            apparent_fk=data["apparent_fk"],
            markdown_summary="",  # not needed for agent pipeline
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_domain_classifier.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full suite for regressions**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/data_analyzer.py core/domain_classifier.py tests/test_data_analyzer.py tests/test_domain_classifier.py
git commit -m "feat: add DomainClassifier Agent 2 — DataProfile to ClassificationResult"
```

---

### Task 3: InsightExtractor Pydantic Models

**Files:**
- Create: `core/insight_extractor.py`
- Test: `tests/test_insight_extractor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_insight_extractor.py`:

```python
"""Tests for core/insight_extractor.py — InsightExtractor and Pydantic models."""
import json
import pytest
from pydantic import ValidationError
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult, DomainClassifier
from core.insight_extractor import InsightReport, InsightExtractor


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


class TestInsightReport:
    def test_valid_insight(self):
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

    def test_rejects_invalid_insight_type(self):
        data = {
            "insights": [
                {
                    "type": "INVALID_TYPE",
                    "table": "Employes",
                    "col": "Nom",
                    "finding": "test",
                    "priority": 1,
                }
            ]
        }
        with pytest.raises(ValidationError):
            InsightReport(**data)

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
        def mock_call(messages, guided_schema=None):
            return json.dumps({
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
            })
        return mock_call

    def test_extract_insights(self, mock_llm, monkeypatch):
        profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
        classifier_result = ClassificationResult(
            archetype="HR", confidence=0.9,
            table_mapping={"employees": "Employes", "absences": "Absences"},
            params={"name_col": "Nom", "department_col": "Departement"},
        )
        extractor = InsightExtractor()
        monkeypatch.setattr(extractor, "_call_llm", lambda msgs, schema: mock_llm(msgs, schema))
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_insight_extractor.py -v 2>&1 | head -15`
Expected: `ModuleNotFoundError: No module named 'core.insight_extractor'`

- [ ] **Step 3: Implement `core/insight_extractor.py`**

Create `core/insight_extractor.py`:

```python
"""Agent 3 — Insight Extractor.

Takes a DataProfile + ClassificationResult and extracts business insights
using vLLM guided_json.

Insights cover: distribution, trend, outlier, relation, kpi
Max 5 insights, sorted by priority.
"""

from __future__ import annotations

import json
import requests
from typing import Any
from pydantic import BaseModel, Field, field_validator

from config import Settings
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult


VALID_INSIGHT_TYPES = [
    "distribution",
    "trend",
    "outlier",
    "relation",
    "kpi",
]


class InsightEntry(BaseModel):
    """Single insight extracted from data analysis."""

    type: str = Field(
        description=f"Type of insight. Must be one of: {', '.join(VALID_INSIGHT_TYPES)}"
    )
    table: str = Field(
        description="Exact table/sheet name from the data"
    )
    col: str = Field(
        description="Exact column name from the data"
    )
    finding: str = Field(
        description="Human-readable finding summary in French"
    )
    priority: int = Field(
        ge=1, le=5,
        description="Priority rank 1-5 (1 = most important)"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_INSIGHT_TYPES:
            raise ValueError(f"type must be one of {VALID_INSIGHT_TYPES}, got '{v}'")
        return v


class InsightReport(BaseModel):
    """Report containing up to 5 business insights."""

    insights: list[InsightEntry] = Field(
        max_length=5,
        description="List of insights, max 5, sorted by priority"
    )


class InsightExtractor:
    """Extracts business insights from data using LLM analysis."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def extract(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
    ) -> InsightReport:
        """Extract business insights from the data.

        Args:
            profile: DataProfile from Agent 1
            classification: ClassificationResult from Agent 2

        Returns:
            InsightReport with up to 5 insights
        """
        prompt = self._build_prompt(profile, classification)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un analyste de données métier. "
                    "Extrayez maximum 5 insights pertinents du profil de données. "
                    "Pour chaque insight, indiquez le type, la table, la colonne concernée, "
                    "et un résumé du résultat en français. "
                    "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        return InsightReport(**self._call_llm(messages))

    def _build_prompt(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
    ) -> str:
        """Build the insight extraction prompt."""
        archetype = classification.archetype
        mapping = classification.table_mapping

        prompt_lines = [
            f"Domaine métier identifié : {archetype}",
            "",
            "Mapping des tables :",
        ]
        for role, table in mapping.items():
            prompt_lines.append(f"  {role} → {table}")

        prompt_lines.extend([
            "",
            "Profil de données :",
            profile.to_json(),
            "",
            "Analysez ces données sous les angles suivants :",
            "  - distribution : répartition des valeurs par catégorie",
            "  - trend : évolutions temporelles",
            "  - outlier : valeurs anomales",
            "  - relation : corrélations entre colonnes/tableaux",
            "  - kpi : indicateurs clés de performance",
            "",
            "Schéma JSON attendu :",
            json.dumps(InsightReport.model_json_schema(), ensure_ascii=False, indent=2),
        ])

        return "\n".join(prompt_lines)

    def _call_llm(self, messages: list[dict]) -> dict[str, Any]:
        """Call vLLM with guided_json schema."""
        url = f"{self.settings.VLLM_BASE_URL}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.3,
            "extra_body": {
                "guided_json": InsightReport.model_json_schema(),
            },
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_insight_extractor.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full suite for regressions**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/insight_extractor.py tests/test_insight_extractor.py
git commit -m "feat: add InsightExtractor Agent 3 — DataProfile + Classification to InsightReport"
```

---

### Task 4: DashboardComposer Pydantic Models

**Files:**
- Create: `core/dashboard_composer.py`
- Test: `tests/test_dashboard_composer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard_composer.py`:

```python
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
        plan = DashboardPlan(pages=[
            PageSection.__pydantic_parent_namespace__ is not None or  # noqa: avoid lint
            type("Page", (), {"name": "Test", "sections": []})()  # placeholder
        ])
        # Just verify model_dump_json works
        plan = DashboardPlan.model_validate({
            "pages": [{"name": "Test", "sections": []}]
        })
        json_str = plan.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["pages"][0]["name"] == "Test"


class TestDashboardComposer:
    @pytest.fixture
    def mock_llm(self, monkeypatch):
        def mock_call(messages, guided_schema=None):
            return json.dumps({
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
            })
        return mock_call

    def test_composes_dashboard(self, mock_llm, monkeypatch):
        composer = DashboardComposer()
        monkeypatch.setattr(composer, "_call_llm", lambda msgs, schema: mock_llm(msgs, schema))
        plan = composer.compose(SAMPLE_CLASSIFICATION, SAMPLE_INSIGHTS)
        assert len(plan.pages) >= 1
        assert "Dashboard RH" in [p.name for p in plan.pages]

    def test_includes_insights_in_prompt(self, mock_llm, monkeypatch):
        composer = DashboardComposer()
        received = []
        def capture(msgs, schema=None):
            received.extend(msgs)
            return mock_llm(msgs, schema)
        monkeypatch.setattr(composer, "_call_llm", capture)
        composer.compose(SAMPLE_CLASSIFICATION, SAMPLE_INSIGHTS)
        prompt_text = " ".join(m.get("content", "") for m in received)
        assert "IT et RH concentrent" in prompt_text
        assert "Pic d'absences" in prompt_text

    def test_self_reflection_pass(self):
        """Verify self-reflection rejects unjustified widgets."""
        plan = DashboardPlan.model_validate({
            "pages": [
                {
                    "name": "Test",
                    "sections": [
                        {
                            "widget": "chart", "chart_type": "bar",
                            "table": "Employes", "x": "Departement",
                            "y": "Nom", "agg": "count",
                            "title": "Justified by insight",
                        },
                    ],
                }
            ]
        })
        # Self-reflection should not raise for valid plan
        validated = plan.self_reflect(SAMPLE_INSIGHTS)
        assert len(validated.pages) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_dashboard_composer.py -v 2>&1 | head -15`
Expected: `ModuleNotFoundError: No module named 'core.dashboard_composer'`

- [ ] **Step 3: Implement `core/dashboard_composer.py`**

Create `core/dashboard_composer.py`:

```python
"""Agent 4 — Dashboard Composer.

Takes a ClassificationResult + InsightReport and composes a DashboardPlan
using vLLM guided_json. Includes a self-reflection pass to validate
that every widget is justified by an insight.
"""

from __future__ import annotations

import json
import requests
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator

from config import Settings
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport


WIDGET_TYPES = ["chart", "table", "card_list", "card", "form"]
CHART_TYPES = ["bar", "line", "pie", "area"]


class PageSection(BaseModel):
    """A single widget section within a dashboard page."""

    widget: str = Field(description=f"Widget type. One of: {', '.join(WIDGET_TYPES)}")
    title: str = Field(description="Human-readable title for the widget")

    # Chart-specific fields (optional, only for widget="chart")
    chart_type: str | None = Field(default=None, description=f"Chart type. One of: {', '.join(CHART_TYPES)}")
    table: str | None = Field(default=None, description="Source table/sheet name")
    x: str | None = Field(default=None, description="X-axis column name")
    y: str | None = Field(default=None, description="Y-axis column name")
    agg: str | None = Field(default=None, description="Aggregation function: count, sum, avg, max, min")

    @field_validator("widget")
    @classmethod
    def validate_widget(cls, v: str) -> str:
        if v not in WIDGET_TYPES:
            raise ValueError(f"widget must be one of {WIDGET_TYPES}, got '{v}'")
        return v

    @field_validator("chart_type")
    @classmethod
    def validate_chart_type(cls, v: str | None) -> str | None:
        if v is not None and v not in CHART_TYPES:
            raise ValueError(f"chart_type must be one of {CHART_TYPES}, got '{v}'")
        return v

    @model_validator(mode="after")
    def validate_chart_fields(self):
        if self.widget == "chart" and not all([self.chart_type, self.table, self.x, self.y, self.agg]):
            raise ValueError("chart widgets require chart_type, table, x, y, and agg fields")
        return self


class Page(BaseModel):
    """A page in the dashboard containing multiple sections."""

    name: str = Field(description="Page name/title")
    sections: list[PageSection] = Field(description="List of widget sections on this page")


class DashboardPlan(BaseModel):
    """Complete dashboard plan with pages and sections."""

    pages: list[Page] = Field(description="List of dashboard pages")

    def self_reflect(self, insights: InsightReport) -> "DashboardPlan":
        """Validate that every widget is justified by an insight.

        Removes widgets whose titles don't match any insight finding.
        Returns a cleaned plan.
        """
        findings_lower = {ins.finding.lower() for ins in insights.insights}

        cleaned_pages = []
        for page in self.pages:
            kept_sections = []
            for section in page.sections:
                if section.widget == "chart" and section.title:
                    title_lower = section.title.lower()
                    matched = any(f in title_lower or title_lower in f for f in findings_lower)
                    if not matched:
                        continue
                kept_sections.append(section)
            if kept_sections:
                cleaned_pages.append(Page(name=page.name, sections=kept_sections))

        return DashboardPlan(pages=cleaned_pages)


class DashboardComposer:
    """Composes a dashboard plan from classification and insights."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
    ) -> DashboardPlan:
        """Compose a dashboard plan.

        Args:
            classification: ClassificationResult from Agent 2
            insights: InsightReport from Agent 3

        Returns:
            DashboardPlan with pages and sections
        """
        prompt = self._build_prompt(classification, insights)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un architecte de dashboards Grist. "
                    "Composez un plan de dashboard basé sur les insights métier fournis. "
                    "Mappez chaque insight à un widget de chart. "
                    "Ajoutez aussi une page formulaire pour la table principale. "
                    "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        raw_plan = DashboardPlan(**self._call_llm(messages))
        return raw_plan.self_reflect(insights)

    def _build_prompt(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
    ) -> str:
        """Build the composition prompt."""
        archetype = classification.archetype
        mapping = classification.table_mapping

        prompt_lines = [
            f"Archetype : {archetype}",
            "",
            "Mapping tables :",
        ]
        for role, table in mapping.items():
            prompt_lines.append(f"  {role} → {table}")

        prompt_lines.extend([
            "",
            "Insights:",
        ])
        for ins in insights.insights:
            prompt_lines.append(f"  [{ins.type}] {ins.table}.{ins.col}: {ins.finding} (priority {ins.priority})")

        prompt_lines.extend([
            "",
            "Pages à créer :",
            "  1. Dashboard principal avec des charts basés sur les insights",
            "  2. Page liste/cards pour la table principale",
            "  3. Page formulaire pour la table principale",
            "",
            "Schéma JSON attendu :",
            json.dumps(DashboardPlan.model_json_schema(), ensure_ascii=False, indent=2),
        ])

        return "\n".join(prompt_lines)

    def _call_llm(self, messages: list[dict]) -> dict[str, Any]:
        """Call vLLM with guided_json schema."""
        url = f"{self.settings.VLLM_BASE_URL}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.3,
            "extra_body": {
                "guided_json": DashboardPlan.model_json_schema(),
            },
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_dashboard_composer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full suite for regressions**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/dashboard_composer.py tests/test_dashboard_composer.py
git commit -m "feat: add DashboardComposer Agent 4 — Classification + Insights to DashboardPlan"
```

---

### Task 5: PipelineOrchestrator

**Files:**
- Create: `core/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
"""Tests for core/pipeline.py — PipelineOrchestrator."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.pipeline import PipelineOrchestrator, PipelineResult
from core.data_analyzer import DataAnalyzer


SAMPLE_XLSX_PATH = "samples/employees_rh.xlsx"


def _mock_profile():
    """Create a minimal DataProfile for testing."""
    from core.data_analyzer import DataProfile
    return DataProfile(
        sheets=["Employes", "Absences"],
        columns={
            "Employes": ["ID", "Nom", "Departement"],
            "Absences": ["ID_Employe", "Date_Debut"],
        },
        stats={},
        apparent_fk=[],
        markdown_summary="# Test",
    )


class TestPipelineResult:
    def test_to_dict_includes_all_stages(self):
        result = PipelineResult(
            profile=_mock_profile(),
            classification=MagicMock(),
            insights=MagicMock(),
            dashboard_plan=MagicMock(),
            errors=[],
        )
        d = result.to_dict()
        assert "profile" in d
        assert "classification" in d
        assert "insights" in d
        assert "dashboard_plan" in d

    def test_save_writes_json(self, tmp_path):
        result = PipelineResult(
            profile=_mock_profile(),
            classification=MagicMock(),
            insights=MagicMock(),
            dashboard_plan=MagicMock(),
            errors=[],
        )
        output_file = tmp_path / "result.json"
        result.save(str(output_file))
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "profile" in data


class TestPipelineOrchestrator:
    @pytest.fixture
    def mock_agents(self):
        """Mock all three LLM agents."""
        classifiers = {}
        extractors = {}
        composers = {}

        def mock_classify(profile):
            from core.domain_classifier import ClassificationResult
            result = ClassificationResult(
                archetype="HR", confidence=0.9,
                table_mapping={"employees": "Employes", "absences": "Absences"},
                params={"name_col": "Nom", "department_col": "Departement"},
            )
            classifiers["called"] = True
            return result

        def mock_extract(profile, classification):
            from core.insight_extractor import InsightReport, InsightEntry
            report = InsightReport(insights=[
                InsightEntry(type="distribution", table="Employes", col="Departement",
                            finding="IT et RH concentrent les effectifs", priority=1),
            ])
            extractors["called"] = True
            return report

        def mock_compose(classification, insights):
            from core.dashboard_composer import DashboardPlan, Page, PageSection
            plan = DashboardPlan(pages=[
                Page(name="Dashboard RH", sections=[
                    PageSection(widget="chart", chart_type="bar", table="Employes",
                               x="Departement", y="Nom", agg="count",
                               title="IT et RH concentrent les effectifs"),
                ]),
            ])
            composers["called"] = True
            return plan

        return mock_classify, mock_extract, mock_compose, classifiers, extractors, composers

    def test_full_pipeline_runs_all_agents(self, mock_agents, monkeypatch, tmp_path):
        mock_classify, mock_extract, mock_compose, _, _, _ = mock_agents
        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        profile = _mock_profile()
        result = orchestrator.run(profile)

        assert isinstance(result, PipelineResult)
        assert result.classification is not None
        assert result.insights is not None
        assert result.dashboard_plan is not None
        assert len(result.errors) == 0

    def test_error_handling_continues_pipeline(self, mock_agents, monkeypatch):
        mock_classify, _, mock_compose, _, _, _ = mock_agents

        def failing_extract(profile, classification):
            raise RuntimeError("LLM timeout")

        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", failing_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        profile = _mock_profile()
        result = orchestrator.run(profile)

        assert len(result.errors) == 1
        assert "LLM timeout" in result.errors[0]
        assert result.classification is not None
        assert result.insights is None
        assert result.dashboard_plan is None

    def test_run_from_file_analyzes_and_processes(self, mock_agents, monkeypatch, tmp_path):
        mock_classify, mock_extract, mock_compose, _, _, _ = mock_agents
        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        # Create a fake xlsx
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK\x03\x04fake")

        result = orchestrator.run_from_file(str(xlsx))

        assert isinstance(result, PipelineResult)
        assert result.classification is not None

    def test_save_output(self, mock_agents, monkeypatch, tmp_path):
        mock_classify, mock_extract, mock_compose, _, _, _ = mock_agents
        orchestrator = PipelineOrchestrator()
        monkeypatch.setattr(orchestrator, "_classify", mock_classify)
        monkeypatch.setattr(orchestrator, "_extract", mock_extract)
        monkeypatch.setattr(orchestrator, "_compose", mock_compose)

        profile = _mock_profile()
        result = orchestrator.run(profile)

        output_dir = tmp_path / "output"
        result.save(str(output_dir))
        assert (output_dir / "pipeline_result.json").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_pipeline.py -v 2>&1 | head -15`
Expected: `ModuleNotFoundError: No module named 'core.pipeline'`

- [ ] **Step 3: Implement `core/pipeline.py`**

Create `core/pipeline.py`:

```python
"""Pipeline Orchestrator — chains Agent 1 → 2 → 3 → 4.

Coordinates the full data-to-dashboard pipeline:
1. DataAnalyzer: Excel → DataProfile
2. DomainClassifier: DataProfile → ClassificationResult
3. InsightExtractor: DataProfile + Classification → InsightReport
4. DashboardComposer: Classification + Insights → DashboardPlan

Handles errors gracefully — if one agent fails, subsequent agents
receive None and the pipeline records the error but continues.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.data_analyzer import DataAnalyzer, DataProfile
from core.domain_classifier import DomainClassifier, ClassificationResult
from core.insight_extractor import InsightExtractor, InsightReport
from core.dashboard_composer import DashboardComposer, DashboardPlan
from config import Settings


@dataclass
class PipelineResult:
    """Result of a full pipeline run."""

    profile: DataProfile | None = None
    classification: ClassificationResult | None = None
    insights: InsightReport | None = None
    dashboard_plan: DashboardPlan | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the pipeline result to a dict."""
        return {
            "profile": self.profile.to_json() if self.profile else None,
            "classification": self.classification.model_dump() if self.classification else None,
            "insights": self.insights.model_dump() if self.insights else None,
            "dashboard_plan": self.dashboard_plan.model_dump() if self.dashboard_plan else None,
            "errors": self.errors,
        }

    def save(self, output_dir: str) -> None:
        """Save the pipeline result to JSON."""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_file = Path(output_dir) / "pipeline_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False, default=str)


class PipelineOrchestrator:
    """Orchestrates the full data-to-dashboard pipeline."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.data_analyzer = DataAnalyzer()
        self.classifier = DomainClassifier(settings)
        self.insight_extractor = InsightExtractor(settings)
        self.composer = DashboardComposer(settings)

    def run(self, profile: DataProfile) -> PipelineResult:
        """Run the full pipeline on a DataProfile.

        Args:
            profile: DataProfile from Agent 1

        Returns:
            PipelineResult with all stages
        """
        result = PipelineResult()

        # Agent 2: Domain Classification
        try:
            result.classification = self._classify(profile)
        except Exception as e:
            result.errors.append(f"DomainClassifier failed: {e}")

        # Agent 3: Insight Extraction
        if result.classification is not None:
            try:
                result.insights = self._extract(profile, result.classification)
            except Exception as e:
                result.errors.append(f"InsightExtractor failed: {e}")

        # Agent 4: Dashboard Composition
        if result.classification is not None and result.insights is not None:
            try:
                result.dashboard_plan = self._compose(result.classification, result.insights)
            except Exception as e:
                result.errors.append(f"DashboardComposer failed: {e}")

        return result

    def run_from_file(self, file_path: str) -> PipelineResult:
        """Run the full pipeline starting from an Excel file.

        Args:
            file_path: Path to the .xlsx file

        Returns:
            PipelineResult with all stages
        """
        profile = self.data_analyzer.analyze(file_path)
        return self.run(profile)

    def _classify(self, profile: DataProfile) -> ClassificationResult:
        """Run Agent 2: Domain Classification."""
        return self.classifier.classify(profile)

    def _extract(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
    ) -> InsightReport:
        """Run Agent 3: Insight Extraction."""
        return self.insight_extractor.extract(profile, classification)

    def _compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
    ) -> DashboardPlan:
        """Run Agent 4: Dashboard Composition."""
        return self.composer.compose(classification, insights)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full suite for regressions**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/pipeline.py tests/test_pipeline.py
git commit -m "feat: add PipelineOrchestrator — chains Agent 1 through Agent 4"
```

---

### Task 6: requirements.txt — add `openai` for guided_json

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add openai dependency**

Append to `requirements.txt`:

```
openai>=1.0.0
```

- [ ] **Step 2: Install**

Run: `pip install openai --break-system-packages 2>&1 | tail -3`
Expected: `Successfully installed openai-...`

- [ ] **Step 3: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add requirements.txt
git commit -m "chore: add openai dependency for vLLM guided_json compatibility"
```

---

### Task 7: Verify all tests pass end-to-end

**Files:**
- All test files

- [ ] **Step 1: Run full suite**

Run: `cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -v 2>&1 | tail -20`
Expected: all tests PASS

- [ ] **Step 2: Verify module imports work**

Run: `cd /home/wderue/workspace/grist-excel && python3 -c "
from core.data_analyzer import DataAnalyzer, DataProfile
from core.domain_classifier import DomainClassifier, ClassificationResult
from core.insight_extractor import InsightExtractor, InsightReport
from core.dashboard_composer import DashboardComposer, DashboardPlan
from core.pipeline import PipelineOrchestrator, PipelineResult
print('All imports OK')
"`
Expected: `All imports OK`

- [ ] **Step 3: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add -A
git commit -m "chore: verify all imports and tests pass"
```

---

## Summary of Changes

| File | Action | Purpose |
|---|---|---|
| `core/data_analyzer.py` | Modified | Add `to_json()` and `from_json()` to `DataProfile` |
| `core/domain_classifier.py` | Created | Agent 2: DataProfile → ClassificationResult |
| `core/insight_extractor.py` | Created | Agent 3: DataProfile + Classification → InsightReport |
| `core/dashboard_composer.py` | Created | Agent 4: Classification + Insights → DashboardPlan |
| `core/pipeline.py` | Created | PipelineOrchestrator: chains agents 1-4 |
| `requirements.txt` | Modified | Add `openai` dependency |
| `tests/test_data_analyzer.py` | Modified | Add `test_to_json_returns_valid_json` |
| `tests/test_domain_classifier.py` | Created | Tests for Agent 2 |
| `tests/test_insight_extractor.py` | Created | Tests for Agent 3 |
| `tests/test_dashboard_composer.py` | Created | Tests for Agent 4 |
| `tests/test_pipeline.py` | Created | Tests for PipelineOrchestrator |

## Total Test Count Added

- Task 1: 1 test (to_json)
- Task 2: 6 tests (ClassificationResult validation, DomainClassifier)
- Task 3: 5 tests (InsightReport validation, InsightExtractor)
- Task 4: 6 tests (PageSection, DashboardPlan, DashboardComposer)
- Task 5: 5 tests (PipelineResult, PipelineOrchestrator)
- **Total: 23 new tests**

## Remaining for Plan C (Archetype Engine)

Not covered in this plan:
- `core/archetype_engine.py` — resolves DashboardPlan → apply_actions calls
- `archetypes/hr.py`, `archetypes/generic.py`, etc. — archetype templates
- `main.py` migration to `--input` CLI
- `prompts/` directory with prompt variants
- `eval_classifier.py` — prompt evaluation tool
