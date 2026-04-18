# Pipeline Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix chart rendering (type inference + field resolution), add Agent 3.5 FeatureEngineer, add Agent 4.5 ReflexionValidator, and add `--debug` mode.

**Architecture:** Chart rendering is broken due to numeric columns mis-typed as Date by `_infer_grist_type`. Fix that first. Then add FeatureEngineer (LLM plans formula cols, executed after import) and ReflexionValidator (deterministic validation + targeted LLM retry). Debug mode prints each agent's JSON output to stdout.

**Tech Stack:** Python 3.11, Pydantic v2, vLLM guided_json, Grist REST API + internal apply_actions, pandas, pytest

---

## Investigation Findings (do not skip)

From inspecting doc `vcq36oDBvwoLgJbMGCKNrV`:
- `_grist_Views_section.options` is **empty string** for ALL chart sections — setting options is NOT needed
- `_grist_Views_section_field.options` is also empty — aggregation is NOT configured via field options
- Root cause of empty charts: `Salaire_Brute` (colRef 8) and `Objectifs_Ateints` (colRef 30) are typed `Date` — pandas datetime parser treats large integers as timestamps
- Pie chart works because `Type` (Text) groups categorically; bar/line fail because numeric y-axis has wrong type

Design spec section "Fix 1 — Chart Rendering" described `options`/`chartSeriesOptions` — investigation proved this wrong. The actual fix is `_infer_grist_type` in `grist_importer.py`.

---

## File Map

| File | Role |
|---|---|
| `core/grist_importer.py` | Fix `_infer_grist_type` — numeric guard before datetime check |
| `archetypes/base.py` | Fix `_add_chart_section` — deduplicate x==y fields, limit fallback to 2 cols |
| `config.py` | Add `DEBUG: bool` setting |
| `core/debug_utils.py` | NEW — `debug_print(label, data, enabled)` helper |
| `main.py` | Add `--debug` flag; call `FeatureEngineer.apply()` after import |
| `core/pipeline.py` | Add `feature_plan` to `PipelineResult`; wire agents 3.5 + 4.5; debug output |
| `core/feature_engineer.py` | NEW — `FeaturePlan` schema + `FeatureEngineer` (LLM planning + Grist apply) |
| `core/dashboard_composer.py` | Update prompt to include engineered col_ids |
| `core/reflexion.py` | NEW — `ReflexionValidator` (deterministic check + LLM retry) |
| `tests/test_grist_importer.py` | Add type inference tests |
| `tests/test_feature_engineer.py` | NEW — unit tests for FeatureEngineer |
| `tests/test_reflexion.py` | NEW — unit tests for ReflexionValidator |

---

## Task 1: Fix `_infer_grist_type` — numeric values mis-typed as Date

**Files:**
- Modify: `core/grist_importer.py:47-102`
- Modify: `tests/test_grist_importer.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_grist_importer.py`:

```python
from core.grist_importer import _infer_grist_type
import pandas as pd

def test_salary_column_is_numeric_not_date():
    """Large integers must not be mis-typed as Date."""
    series = pd.Series([30739, 55872, 97639, 42000, 85000])
    assert _infer_grist_type(series) == "Numeric"

def test_integer_column_is_int():
    series = pd.Series([1, 2, 3, 4, 5])
    assert _infer_grist_type(series) == "Int"

def test_score_column_is_numeric_not_date():
    """Float scores (0.0–5.0 range) must not be mis-typed."""
    series = pd.Series([3.5, 4.0, 2.5, 5.0, 1.0])
    assert _infer_grist_type(series) == "Numeric"

def test_actual_date_string_column_is_date():
    series = pd.Series(["2024-01-15", "2023-06-30", "2022-12-01"])
    assert _infer_grist_type(series) in ("Date", "DateTime")

def test_boolean_column_is_toggle():
    series = pd.Series(["oui", "non", "oui", "oui"])
    assert _infer_grist_type(series) == "Toggle"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source venv/bin/activate
pytest tests/test_grist_importer.py::test_salary_column_is_numeric_not_date tests/test_grist_importer.py::test_score_column_is_numeric_not_date -v
```

Expected: FAIL — `_infer_grist_type` returns `"Date"` for integer salary values.

- [ ] **Step 3: Fix `_infer_grist_type` in `core/grist_importer.py`**

Replace the full function:

```python
def _infer_grist_type(series: pd.Series) -> str:
    """Infer Grist column type from a pandas Series."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return "Text"

    # Check boolean/toggle first (before numeric, to catch "oui"/"non")
    try:
        bool_vals = {"true", "false", "vrai", "faux", "oui", "non", "1", "0"}
        if all(str(v).lower() in bool_vals for v in non_null):
            return "Toggle"
    except (ValueError, TypeError):
        pass

    # Check integer — pure digit strings or Python ints
    try:
        all_int = True
        for v in non_null:
            s = str(v).strip().lstrip("-")
            if not s.isdigit():
                all_int = False
                break
        if all_int:
            return "Int"
    except (ValueError, TypeError):
        pass

    # Check numeric float — BEFORE datetime (prevents large ints being read as timestamps)
    try:
        floats = [float(v) for v in non_null if not pd.isna(v)]
        if floats:
            return "Numeric"
    except (ValueError, TypeError):
        pass

    # Check datetime — only if values are non-numeric strings
    # (guards against pandas treating large integers as nanosecond timestamps)
    try:
        if all(isinstance(v, str) for v in non_null):
            parsed = pd.to_datetime(non_null, errors="coerce")
            if parsed.notna().all():
                is_date_only = all(
                    not (hasattr(v, "hour") and v.hour)
                    for v in non_null.head(100)
                )
                return "Date" if is_date_only else "DateTime"
    except (ValueError, TypeError):
        pass

    return "Text"
```

- [ ] **Step 4: Run all type inference tests**

```bash
pytest tests/test_grist_importer.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/grist_importer.py tests/test_grist_importer.py
git commit -m "fix: _infer_grist_type — numeric guard before datetime check prevents salary/score mis-typed as Date"
```

---

## Task 2: Fix chart field resolution in `base.py`

Two bugs: (a) duplicate field when x==y, (b) fallback adds all columns instead of 2.

**Files:**
- Modify: `archetypes/base.py` — `_add_chart_section`

- [ ] **Step 1: Write failing tests**

Create `tests/test_base_archetype.py`:

```python
from unittest.mock import MagicMock, call, patch
from archetypes.base import BaseArchetype


class ConcreteArchetype(BaseArchetype):
    def apply(self, api, doc_id, classification, plan):
        return []


def _make_api(col_map):
    """Mock GristAPI with given {colId: colRef} map for table_ref=1."""
    api = MagicMock()
    api.apply_actions.return_value = {"retValues": [99]}
    # _get_col_ref_map returns col_map
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

    # apply_actions called twice: once for section, once for fields
    field_call_args = api.apply_actions.call_args_list[1][0][1]
    col_refs_added = [a[3]["colRef"] for a in field_call_args]
    assert col_refs_added.count(8) == 1, "same colRef must not be added twice"


def test_chart_fallback_adds_only_two_cols():
    """When x/y resolution fails, fallback adds at most 2 columns."""
    arch = ConcreteArchetype()
    col_map = {f"Col{i}": i for i in range(1, 8)}
    api = _make_api(col_map)

    arch._add_chart_section(api, "doc1", 1, 1, "bar", "Test", x_col=None, y_col=None)

    field_call_args = api.apply_actions.call_args_list[1][0][1]
    col_refs_added = [a[3]["colRef"] for a in field_call_args]
    assert len(col_refs_added) <= 2, f"fallback must add ≤2 cols, got {len(col_refs_added)}"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_base_archetype.py -v
```

Expected: FAIL.

- [ ] **Step 3: Fix `_add_chart_section` in `archetypes/base.py`**

Replace only the field-selection logic at the end of `_add_chart_section` (after `result = api.apply_actions(...)`):

```python
        section_id: int = result["retValues"][0]
        col_map = self._get_col_ref_map(api, doc_id, table_ref)

        def resolve(name: str | None) -> int | None:
            if not name:
                return None
            if name in col_map:
                return col_map[name]
            norm = _normalize(name)
            for col_id, ref in col_map.items():
                if _normalize(col_id) == norm:
                    return ref
            return None

        x_ref = resolve(x_col)
        y_ref = resolve(y_col)

        if x_ref and y_ref and x_ref != y_ref:
            col_refs = [x_ref, y_ref]
        elif x_ref:
            col_refs = [x_ref]
        else:
            # Fallback: first 2 cols only (not all — avoids polluting chart with irrelevant fields)
            col_refs = list(col_map.values())[:2]

        self._add_section_fields(api, doc_id, section_id, col_refs)
        return section_id
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_base_archetype.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add archetypes/base.py tests/test_base_archetype.py
git commit -m "fix: chart field resolution — deduplicate x==y colRef, limit fallback to 2 cols"
```

---

## Task 3: Debug mode — config + helper

**Files:**
- Modify: `config.py`
- Create: `core/debug_utils.py`

- [ ] **Step 1: Add `DEBUG` to `config.py`**

Add field to `Settings` class in `config.py`:

```python
DEBUG: bool = False
```

Full updated Settings block (add after `TIMEOUT_GRIST`):

```python
DEBUG: bool = False
```

- [ ] **Step 2: Create `core/debug_utils.py`**

```python
"""Debug output utility for pipeline steps."""

from __future__ import annotations
import json
from typing import Any


def debug_print(label: str, data: Any, enabled: bool = False) -> None:
    """Print step output when debug mode is active.

    Args:
        label: Step name shown in header (e.g. "Agent 1 — DataAnalyzer")
        data: Object to print. Must support model_dump() (Pydantic) or to_json() or be a dict/str.
        enabled: If False, no-op.
    """
    if not enabled:
        return
    print(f"\n[DEBUG {label}]")
    if hasattr(data, "model_dump"):
        print(json.dumps(data.model_dump(), indent=2, ensure_ascii=False, default=str))
    elif hasattr(data, "to_json"):
        print(data.to_json())
    elif isinstance(data, dict):
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        print(str(data))
```

- [ ] **Step 3: Commit**

```bash
git add config.py core/debug_utils.py
git commit -m "feat: add DEBUG config + debug_print helper"
```

---

## Task 4: Debug mode — `--debug` flag in `main.py` + pipeline output

**Files:**
- Modify: `main.py`
- Modify: `core/pipeline.py`

- [ ] **Step 1: Add `--debug` to `main.py` argparse**

In `main.py`, add to the parser after the `--dry-run` argument:

```python
    parser.add_argument(
        "--debug", action="store_true",
        help="Afficher la sortie JSON de chaque étape du pipeline"
    )
```

Then update the Settings construction and pass debug through:

```python
    args = parser.parse_args()
    settings = Settings(DEBUG=args.debug)
```

- [ ] **Step 2: Add debug output to `pipeline.py`**

Import `debug_print` at the top of `core/pipeline.py`:

```python
from core.debug_utils import debug_print
```

In `PipelineOrchestrator.__init__`, store settings:

```python
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.debug = self.settings.DEBUG
        ...
```

In `PipelineOrchestrator.run()`, add debug calls after each agent result:

```python
    def run(self, profile: DataProfile) -> PipelineResult:
        result = PipelineResult()
        result.profile = profile
        debug_print("Agent 1 — DataAnalyzer", profile, self.debug)

        try:
            result.classification = self._classify(profile)
            debug_print("Agent 2 — DomainClassifier", result.classification, self.debug)
        except Exception as e:
            result.errors.append(f"DomainClassifier failed: {e}")

        if result.classification is not None:
            try:
                result.insights = self._extract(profile, result.classification)
                debug_print("Agent 3 — InsightExtractor", result.insights, self.debug)
            except Exception as e:
                result.errors.append(f"InsightExtractor failed: {e}")

        if result.classification is not None and result.insights is not None:
            try:
                result.dashboard_plan = self._compose(result.classification, result.insights)
                debug_print("Agent 4 — DashboardComposer", result.dashboard_plan, self.debug)
            except Exception as e:
                result.errors.append(f"DashboardComposer failed: {e}")

        return result
```

Also add `profile` field to `PipelineResult`:

```python
@dataclass
class PipelineResult:
    profile: DataProfile | None = None
    classification: ClassificationResult | None = None
    insights: InsightReport | None = None
    dashboard_plan: DashboardPlan | None = None
    errors: list[str] = field(default_factory=list)
```

And in `to_dict()`:

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": json.loads(self.profile.to_json()) if self.profile else None,
            "classification": self.classification.model_dump() if self.classification else None,
            "insights": self.insights.model_dump() if self.insights else None,
            "dashboard_plan": self.dashboard_plan.model_dump() if self.dashboard_plan else None,
            "errors": self.errors,
        }
```

- [ ] **Step 3: Test debug flag works**

```bash
source venv/bin/activate
python3 main.py --input samples/employees_rh.xlsx --dry-run --debug 2>&1 | head -60
```

Expected: see `[DEBUG Agent 1 — DataAnalyzer]` block followed by DataProfile JSON.

- [ ] **Step 4: Commit**

```bash
git add main.py core/pipeline.py
git commit -m "feat: add --debug flag — prints JSON output of each pipeline agent to stdout"
```

---

## Task 5: `FeaturePlan` schema + `FeatureEngineer` skeleton

**Files:**
- Create: `core/feature_engineer.py`
- Create: `tests/test_feature_engineer.py`

- [ ] **Step 1: Write failing schema test**

Create `tests/test_feature_engineer.py`:

```python
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
```

- [ ] **Step 2: Run — verify fail**

```bash
pytest tests/test_feature_engineer.py -v
```

Expected: FAIL — `core.feature_engineer` not found.

- [ ] **Step 3: Create `core/feature_engineer.py` with schema**

```python
"""Agent 3.5 — Feature Engineer.

Plans and applies Grist formula columns derived from LLM insights.
Two-phase:
  1. plan() — LLM generates FeaturePlan (formula columns to create)
  2. apply() — writes formula cols to live Grist document via PATCH API
"""

from __future__ import annotations

import json
import logging
import re
import requests
from typing import Any

from pydantic import BaseModel, Field

from config import Settings
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport

logger = logging.getLogger(__name__)


class FormulaColumn(BaseModel):
    """A derived Grist column defined by a Python formula."""

    table: str = Field(description="Semantic table role (key in table_mapping, e.g. 'employees')")
    col_id: str = Field(description="Grist column ID — ASCII only, no spaces")
    label: str = Field(description="Human-readable label (French)")
    type: str = Field(description="Grist type: Toggle, Int, Numeric, Text")
    formula: str = Field(description="Grist Python formula using $ColName and Table.lookupRecords() syntax")


class FeaturePlan(BaseModel):
    """Plan of derived columns to create in the Grist document."""

    features: list[FormulaColumn] = Field(
        default_factory=list,
        max_length=6,
        description="Derived columns to create (0–6)",
    )
```

- [ ] **Step 4: Run schema tests**

```bash
pytest tests/test_feature_engineer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/feature_engineer.py tests/test_feature_engineer.py
git commit -m "feat: add FeaturePlan schema + FormulaColumn model"
```

---

## Task 6: `FeatureEngineer` LLM planning

**Files:**
- Modify: `core/feature_engineer.py`
- Modify: `tests/test_feature_engineer.py`

- [ ] **Step 1: Write failing test for `plan()` method**

Add to `tests/test_feature_engineer.py`:

```python
from unittest.mock import patch, MagicMock
from core.feature_engineer import FeatureEngineer
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightEntry


def _make_profile():
    p = DataProfile.__new__(DataProfile)
    p.sheets = ["Employés"]
    p.columns = {"Employés": ["ID_Employe", "Salaire_Brute", "Manager"]}
    p.apparent_fk = []
    p.stats = {}
    return p


def _make_classification():
    return ClassificationResult(
        archetype="HR",
        confidence=0.95,
        table_mapping={"employees": "Employés"},
        params={},
    )


def _make_insights():
    return InsightReport(insights=[
        InsightEntry(type="outlier", table="Employés", col="Manager",
                     finding="6 null managers", priority=1),
    ])


def test_feature_engineer_plan_calls_llm():
    eng = FeatureEngineer()
    mock_response = {
        "features": [{
            "table": "employees",
            "col_id": "sans_manager",
            "label": "Sans Manager",
            "type": "Toggle",
            "formula": "not bool($Manager)",
        }]
    }
    with patch.object(eng, "_call_llm", return_value=mock_response) as mock_llm:
        plan = eng.plan(_make_profile(), _make_classification(), _make_insights())
    mock_llm.assert_called_once()
    assert len(plan.features) == 1
    assert plan.features[0].col_id == "sans_manager"
```

- [ ] **Step 2: Run — verify fail**

```bash
pytest tests/test_feature_engineer.py::test_feature_engineer_plan_calls_llm -v
```

Expected: FAIL — `FeatureEngineer` has no `plan` method.

- [ ] **Step 3: Add `FeatureEngineer` class with `plan()` + `_build_prompt()` + `_call_llm()`**

Append to `core/feature_engineer.py`:

```python

GRIST_FORMULA_EXAMPLES = """
# Count related records
len(Absences.lookupRecords(ID_Employe=$ID_Employe))

# Boolean existence check (returns True/False)
bool(Evaluations.lookupOne(ID_Employe=$ID_Employe).ID_Employe)

# Numeric bucketing
"Haut" if $Salaire_Brute > 70000 else ("Moyen" if $Salaire_Brute > 45000 else "Bas")

# Average from related table (safe division)
(sum(Evaluations.lookupRecords(ID_Employe=$ID_Employe).Note) /
 max(len(Evaluations.lookupRecords(ID_Employe=$ID_Employe)), 1))

# Days since a date column
(TODAY() - $Date_Embauche).days if $Date_Embauche else 0

# Boolean null check
not bool($Manager)
"""


class FeatureEngineer:
    """Plans and applies derived Grist formula columns."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def plan(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
    ) -> FeaturePlan:
        """Ask LLM to generate derived columns that make insights chartable.

        Returns:
            FeaturePlan with 0–6 FormulaColumn entries.
        """
        prompt = self._build_prompt(profile, classification, insights)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un ingénieur de données Grist. "
                    "Générez des colonnes de formule Grist Python pour rendre les insights chartables. "
                    "Utilisez UNIQUEMENT les noms de colonnes fournis. "
                    "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        data = self._call_llm(messages)
        return FeaturePlan(**data)

    def _build_prompt(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
    ) -> str:
        lines = [
            f"Archetype : {classification.archetype}",
            "",
            "Tables et colonnes disponibles :",
        ]
        for role, table_name in classification.table_mapping.items():
            cols = profile.columns.get(table_name, [])
            lines.append(f"  {role} ({table_name}): {', '.join(cols)}")

        lines.extend([
            "",
            "Insights à rendre chartables :",
        ])
        for ins in insights.insights:
            lines.append(f"  [{ins.type}] {ins.table}.{ins.col}: {ins.finding}")

        lines.extend([
            "",
            "Exemples de formules Grist Python valides :",
            GRIST_FORMULA_EXAMPLES,
            "",
            "Règles :",
            "  - col_id: ASCII uniquement, pas d'espaces, pas d'accents",
            "  - table: clé sémantique du mapping (ex: 'employees', 'absences')",
            "  - Référencez des tables exactement comme dans le mapping",
            "  - 0 features si aucun insight ne nécessite de colonne dérivée",
            "",
            "Schéma JSON attendu :",
            json.dumps(FeaturePlan.model_json_schema(), ensure_ascii=False, indent=2),
        ])
        return "\n".join(lines)

    def _call_llm(
        self,
        messages: list[dict],
        schema: dict[str, Any] | None = None,
        *,
        _retry: bool = False,
    ) -> dict[str, Any]:
        """Call vLLM with guided_json schema. Retries once on JSON decode failure."""
        effective_schema = schema or FeaturePlan.model_json_schema()
        url = f"{self.settings.VLLM_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.2,
            "chat_template_kwargs": {"enable_thinking": False},
            "extra_body": {"guided_json": effective_schema},
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning")
        if content is None:
            raise ValueError("Empty response from LLM")
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            content = json_match.group(0)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            if _retry:
                raise ValueError(f"LLM returned invalid JSON after retry: {content!r}") from exc
            logger.warning("JSON decode failed, retrying with stricter prompt.")
            stricter = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "Votre réponse n'est pas du JSON valide. "
                    "Répondez UNIQUEMENT avec du JSON valide sans texte supplémentaire."
                )},
            ]
            return self._call_llm(stricter, schema=effective_schema, _retry=True)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_feature_engineer.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/feature_engineer.py tests/test_feature_engineer.py
git commit -m "feat: FeatureEngineer.plan() — LLM generates Grist formula columns from insights"
```

---

## Task 7: `FeatureEngineer.apply()` — write formula cols to Grist

**Files:**
- Modify: `core/feature_engineer.py`
- Modify: `tests/test_feature_engineer.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_feature_engineer.py`:

```python
from unittest.mock import MagicMock, patch
from core.feature_engineer import FeatureEngineer, FeaturePlan, FormulaColumn
from core.grist_api import GristAPI


def test_apply_patches_formula_column():
    eng = FeatureEngineer()
    api = MagicMock(spec=GristAPI)
    api.get_records.return_value = []  # no error in record fetch

    plan = FeaturePlan(features=[
        FormulaColumn(
            table="employees",
            col_id="nb_absences",
            label="Nb Absences",
            type="Int",
            formula="len(Absences.lookupRecords(ID_Employe=$ID_Employe))",
        )
    ])
    table_mapping = {"employees": "Employes"}

    applied, failed = eng.apply(api, "doc123", plan, table_mapping)

    api.patch_columns.assert_called_once_with(
        "doc123",
        "Employes",
        [{
            "id": "nb_absences",
            "fields": {
                "type": "Int",
                "label": "Nb Absences",
                "formula": "len(Absences.lookupRecords(ID_Employe=$ID_Employe))",
                "isFormula": True,
            },
        }],
    )
    assert "nb_absences" in applied
    assert failed == []


def test_apply_skips_on_api_error():
    eng = FeatureEngineer()
    api = MagicMock(spec=GristAPI)
    api.patch_columns.side_effect = Exception("API error")

    plan = FeaturePlan(features=[
        FormulaColumn(
            table="employees", col_id="bad_col", label="Bad", type="Text", formula="$X"
        )
    ])
    applied, failed = eng.apply(api, "doc123", plan, {"employees": "Employes"})

    assert applied == []
    assert "bad_col" in failed
```

- [ ] **Step 2: Run — verify fail**

```bash
pytest tests/test_feature_engineer.py::test_apply_patches_formula_column tests/test_feature_engineer.py::test_apply_skips_on_api_error -v
```

Expected: FAIL — `apply` method not defined.

- [ ] **Step 3: Add `apply()` to `FeatureEngineer` in `core/feature_engineer.py`**

Add after the `_call_llm` method:

```python
    def apply(
        self,
        api: Any,
        doc_id: str,
        plan: FeaturePlan,
        table_mapping: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        """Write formula columns from FeaturePlan to a live Grist document.

        Args:
            api: GristAPI instance
            doc_id: Target Grist document ID
            plan: FeaturePlan with FormulaColumn entries
            table_mapping: semantic role → actual Grist tableId

        Returns:
            (applied_col_ids, failed_col_ids)
        """
        applied: list[str] = []
        failed: list[str] = []

        for feature in plan.features:
            table_id = table_mapping.get(feature.table, feature.table)
            try:
                api.patch_columns(doc_id, table_id, [{
                    "id": feature.col_id,
                    "fields": {
                        "type": feature.type,
                        "label": feature.label,
                        "formula": feature.formula,
                        "isFormula": True,
                    },
                }])
                # Validate: fetch 1 record — if Grist formula error, column may exist but compute nothing
                # Surface-level check only; deep formula validation requires Grist sandbox
                api.get_records(doc_id, table_id)
                applied.append(feature.col_id)
                logger.info("Feature column applied: %s.%s", table_id, feature.col_id)
            except Exception as exc:
                logger.warning("Feature column failed: %s.%s — %s", table_id, feature.col_id, exc)
                failed.append(feature.col_id)

        return applied, failed
```

Add `from typing import Any` at the top if not already present. (It already is.)

- [ ] **Step 4: Run all feature engineer tests**

```bash
pytest tests/test_feature_engineer.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/feature_engineer.py tests/test_feature_engineer.py
git commit -m "feat: FeatureEngineer.apply() — patches Grist formula columns from FeaturePlan"
```

---

## Task 8: Integrate `FeatureEngineer` into pipeline and `main.py`

**Files:**
- Modify: `core/pipeline.py`
- Modify: `core/dashboard_composer.py`
- Modify: `main.py`

- [ ] **Step 1: Add `feature_plan` to `PipelineResult` and wire Agent 3.5**

In `core/pipeline.py`:

Add import:

```python
from core.feature_engineer import FeatureEngineer, FeaturePlan
from core.debug_utils import debug_print
```

Add field to `PipelineResult`:

```python
@dataclass
class PipelineResult:
    profile: DataProfile | None = None
    classification: ClassificationResult | None = None
    insights: InsightReport | None = None
    feature_plan: FeaturePlan | None = None
    dashboard_plan: DashboardPlan | None = None
    errors: list[str] = field(default_factory=list)
```

Update `to_dict()`:

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": json.loads(self.profile.to_json()) if self.profile else None,
            "classification": self.classification.model_dump() if self.classification else None,
            "insights": self.insights.model_dump() if self.insights else None,
            "feature_plan": self.feature_plan.model_dump() if self.feature_plan else None,
            "dashboard_plan": self.dashboard_plan.model_dump() if self.dashboard_plan else None,
            "errors": self.errors,
        }
```

Add `feature_engineer` to `PipelineOrchestrator.__init__`:

```python
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.debug = self.settings.DEBUG
        self.data_analyzer = DataAnalyzer(settings)
        self.classifier = DomainClassifier(settings)
        self.insight_extractor = InsightExtractor(settings)
        self.feature_engineer = FeatureEngineer(settings)
        self.composer = DashboardComposer(settings)
```

In `PipelineOrchestrator.run()`, add Agent 3.5 after insight extraction:

```python
        # Agent 3.5: Feature Engineering
        if result.classification is not None and result.insights is not None:
            try:
                result.feature_plan = self.feature_engineer.plan(
                    profile, result.classification, result.insights
                )
                debug_print("Agent 3.5 — FeatureEngineer", result.feature_plan, self.debug)
            except Exception as e:
                result.errors.append(f"FeatureEngineer failed: {e}")
                result.feature_plan = FeaturePlan(features=[])
```

- [ ] **Step 2: Pass engineered col_ids to `DashboardComposer`**

In `core/dashboard_composer.py`, update `compose()` signature:

```python
    def compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
    ) -> DashboardPlan:
```

Update `_build_prompt()` to accept and include `feature_plan`:

```python
    def _build_prompt(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
    ) -> str:
        ...
        # After the insights section, add:
        if feature_plan and feature_plan.features:
            prompt_lines.extend([
                "",
                "Colonnes dérivées disponibles (créées par FeatureEngineer) :",
            ])
            for f in feature_plan.features:
                table_id = classification.table_mapping.get(f.table, f.table)
                prompt_lines.append(f"  {table_id}.{f.col_id} ({f.type}) : {f.label}")
```

Pass `feature_plan` through in `compose()`:

```python
        prompt = self._build_prompt(classification, insights, feature_plan)
```

Update `_compose()` in `pipeline.py`:

```python
    def _compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
    ) -> DashboardPlan:
        return self.composer.compose(classification, insights, feature_plan)
```

And in `run()`, pass `result.feature_plan`:

```python
        if result.classification is not None and result.insights is not None:
            try:
                result.dashboard_plan = self._compose(
                    result.classification, result.insights, result.feature_plan
                )
                debug_print("Agent 4 — DashboardComposer", result.dashboard_plan, self.debug)
            except Exception as e:
                result.errors.append(f"DashboardComposer failed: {e}")
```

- [ ] **Step 3: Add `FeatureEngineer.apply()` call to `main.py`**

In `main.py`, after step 3 (import), before step 4 (archetype):

```python
    # Step 3b: Apply engineered formula columns
    if result.feature_plan and result.feature_plan.features:
        print("\n[3b/4] Application des colonnes dérivées...")
        from core.feature_engineer import FeatureEngineer
        fe = FeatureEngineer(settings)
        applied, failed = fe.apply(api, doc_id, result.feature_plan, result.classification.table_mapping)
        print(f"  Colonnes appliquées : {applied}")
        if failed:
            print(f"  Colonnes échouées  : {failed}")
        if settings.DEBUG:
            from core.debug_utils import debug_print
            debug_print("FeatureEngineer.apply", {"applied": applied, "failed": failed}, True)
```

- [ ] **Step 4: Smoke test**

```bash
source venv/bin/activate
python3 main.py --input samples/employees_rh.xlsx --dry-run --debug 2>&1 | grep -A5 "FeatureEngineer"
```

Expected: see `[DEBUG Agent 3.5 — FeatureEngineer]` with features JSON.

- [ ] **Step 5: Commit**

```bash
git add core/pipeline.py core/dashboard_composer.py main.py
git commit -m "feat: integrate FeatureEngineer into pipeline — plan before compose, apply after import"
```

---

## Task 9: `ReflexionValidator` — deterministic validation

**Files:**
- Create: `core/reflexion.py`
- Create: `tests/test_reflexion.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_reflexion.py`:

```python
from core.reflexion import ReflexionValidator
from core.dashboard_composer import DashboardPlan, Page, PageSection


def _make_plan(sections: list[dict]) -> DashboardPlan:
    return DashboardPlan(pages=[Page(name="Test", sections=[
        PageSection(**s) for s in sections
    ])])


RAW_COLS = {"Employes": ["ID_Employe", "Salaire_Brute", "Manager"]}
ENG_COLS = {"Employes": ["nb_absences", "sans_manager"]}
MAPPING = {"employees": "Employes"}


def test_valid_chart_survives():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "bar",
        "table": "employees", "x": "ID_Employe", "y": "Salaire_Brute",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 1
    assert len(result.pages[0].sections) == 1


def test_chart_with_missing_x_col_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "bar",
        "table": "employees", "x": "NonExistent", "y": "Salaire_Brute",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 0  # page dropped (0 sections left)


def test_engineered_col_survives():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "pie",
        "table": "employees", "x": "Manager", "y": "nb_absences",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages[0].sections) == 1


def test_card_list_with_valid_table_survives():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{"widget": "card_list", "title": "T", "table": "employees"}])
    result = validator.validate_deterministic(plan)
    assert len(result.pages[0].sections) == 1


def test_card_list_with_unknown_table_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{"widget": "card_list", "title": "T", "table": "ghost_table"}])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 0


def test_empty_page_after_drops_is_removed():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    plan = _make_plan([{
        "widget": "chart", "title": "T", "chart_type": "bar",
        "table": "employees", "x": "BadCol", "y": "AlsoBad",
    }])
    result = validator.validate_deterministic(plan)
    assert len(result.pages) == 0


def test_drop_ratio_above_half():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    good = {"widget": "card_list", "title": "Good", "table": "employees"}
    bad1 = {"widget": "chart", "title": "B1", "chart_type": "bar",
            "table": "employees", "x": "X1", "y": "Y1"}
    bad2 = {"widget": "chart", "title": "B2", "chart_type": "bar",
            "table": "employees", "x": "X2", "y": "Y2"}
    plan = _make_plan([good, bad1, bad2])
    _, drop_ratio = validator._validate_and_count(plan)
    assert drop_ratio > 0.5
```

- [ ] **Step 2: Run — verify fail**

```bash
pytest tests/test_reflexion.py -v
```

Expected: FAIL — `core.reflexion` not found.

- [ ] **Step 3: Create `core/reflexion.py` with deterministic validation**

```python
"""Agent 4.5 — Reflexion Validator.

Deterministic validation of DashboardPlan:
- Verifies every chart column exists (raw or engineered)
- Drops invalid sections; removes empty pages
- If >50% dropped, triggers targeted LLM retry via DashboardComposer
"""

from __future__ import annotations

import logging
import unicodedata
from typing import TYPE_CHECKING

from core.dashboard_composer import DashboardPlan, Page, PageSection

if TYPE_CHECKING:
    from core.dashboard_composer import DashboardComposer
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


class ReflexionValidator:
    """Validates DashboardPlan column references and drops/retries invalid sections."""

    def __init__(
        self,
        raw_cols: dict[str, list[str]],
        engineered_cols: dict[str, list[str]],
        table_mapping: dict[str, str],
    ):
        """
        Args:
            raw_cols: {actual_table_id: [col_id, ...]} from DataProfile.columns
            engineered_cols: {actual_table_id: [col_id, ...]} from FeaturePlan
            table_mapping: {semantic_role: actual_table_id} from ClassificationResult
        """
        self.raw_cols = raw_cols
        self.engineered_cols = engineered_cols
        self.table_mapping = table_mapping

    def _resolve_table(self, semantic_table: str) -> str | None:
        """Resolve semantic role → actual tableId. Returns None if unresolvable."""
        if semantic_table in self.table_mapping:
            return self.table_mapping[semantic_table]
        # Accent-insensitive fallback
        norm = _normalize(semantic_table)
        for role, actual in self.table_mapping.items():
            if _normalize(role) == norm:
                return actual
        # Direct tableId match (LLM may use actual name)
        all_tables = set(self.raw_cols.keys()) | set(self.engineered_cols.keys())
        for t in all_tables:
            if _normalize(t) == norm:
                return t
        return None

    def _col_exists(self, table_id: str, col_name: str) -> bool:
        """Check if col_name exists in raw or engineered cols for table_id."""
        all_cols = (
            self.raw_cols.get(table_id, [])
            + self.engineered_cols.get(table_id, [])
        )
        norm = _normalize(col_name)
        return any(_normalize(c) == norm for c in all_cols)

    def _validate_section(self, section: PageSection) -> tuple[bool, str]:
        """Return (is_valid, reason_if_dropped)."""
        table_id = self._resolve_table(section.table or "")
        if table_id is None:
            return False, f"table '{section.table}' unresolvable"

        if section.widget == "chart":
            if section.x and not self._col_exists(table_id, section.x):
                return False, f"x col '{section.x}' not in {table_id}"
            if section.y and not self._col_exists(table_id, section.y):
                return False, f"y col '{section.y}' not in {table_id}"

        return True, ""

    def _validate_and_count(self, plan: DashboardPlan) -> tuple[DashboardPlan, float]:
        """Run deterministic validation. Returns (cleaned_plan, drop_ratio)."""
        total = sum(len(p.sections) for p in plan.pages)
        dropped = 0
        cleaned_pages: list[Page] = []

        for page in plan.pages:
            kept: list[PageSection] = []
            for section in page.sections:
                valid, reason = self._validate_section(section)
                if valid:
                    kept.append(section)
                else:
                    dropped += 1
                    logger.warning("Dropped section '%s': %s", section.title, reason)
            if kept:
                cleaned_pages.append(Page(name=page.name, sections=kept))

        drop_ratio = dropped / total if total > 0 else 0.0
        return DashboardPlan(pages=cleaned_pages), drop_ratio

    def validate_deterministic(self, plan: DashboardPlan) -> DashboardPlan:
        """Run validation without LLM retry. Returns cleaned plan."""
        cleaned, _ = self._validate_and_count(plan)
        return cleaned
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_reflexion.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/reflexion.py tests/test_reflexion.py
git commit -m "feat: ReflexionValidator — deterministic chart column validation"
```

---

## Task 10: `ReflexionValidator` — LLM retry when >50% dropped

**Files:**
- Modify: `core/reflexion.py`
- Modify: `tests/test_reflexion.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_reflexion.py`:

```python
from unittest.mock import MagicMock
from core.dashboard_composer import DashboardComposer, InsightReport, ClassificationResult


def test_validate_triggers_retry_when_over_half_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)

    # 1 good, 2 bad → 66% dropped → should trigger retry
    good = PageSection(widget="card_list", title="Good", table="employees")
    bad1 = PageSection(widget="chart", title="B1", chart_type="bar",
                       table="employees", x="X1", y="Y1")
    bad2 = PageSection(widget="chart", title="B2", chart_type="bar",
                       table="employees", x="X2", y="Y2")
    original_plan = DashboardPlan(pages=[Page(name="P", sections=[good, bad1, bad2])])

    retry_plan = DashboardPlan(pages=[Page(name="P", sections=[good])])
    mock_composer = MagicMock(spec=DashboardComposer)
    mock_composer.compose.return_value = retry_plan

    mock_classification = MagicMock()
    mock_classification.archetype = "HR"
    mock_classification.table_mapping = MAPPING
    mock_insights = MagicMock()
    mock_insights.insights = []

    result = validator.validate(
        original_plan, mock_classification, mock_insights, mock_composer
    )

    mock_composer.compose.assert_called_once()
    assert len(result.pages[0].sections) == 1
    assert result.pages[0].sections[0].title == "Good"


def test_validate_no_retry_when_under_half_dropped():
    validator = ReflexionValidator(RAW_COLS, ENG_COLS, MAPPING)
    good1 = PageSection(widget="card_list", title="G1", table="employees")
    good2 = PageSection(widget="card_list", title="G2", table="employees")
    bad = PageSection(widget="chart", title="B", chart_type="bar",
                      table="employees", x="BadX", y="BadY")
    plan = DashboardPlan(pages=[Page(name="P", sections=[good1, good2, bad])])

    mock_composer = MagicMock(spec=DashboardComposer)
    result = validator.validate(plan, MagicMock(), MagicMock(), mock_composer)

    mock_composer.compose.assert_not_called()
    assert len(result.pages[0].sections) == 2
```

- [ ] **Step 2: Run — verify fail**

```bash
pytest tests/test_reflexion.py::test_validate_triggers_retry_when_over_half_dropped -v
```

Expected: FAIL — `validate` method not defined.

- [ ] **Step 3: Add `validate()` + `_build_retry_context()` to `ReflexionValidator`**

Append to `ReflexionValidator` class in `core/reflexion.py`:

```python
    def validate(
        self,
        plan: DashboardPlan,
        classification: "ClassificationResult",
        insights: "InsightReport",
        composer: "DashboardComposer",
    ) -> DashboardPlan:
        """Validate plan. If >50% dropped, retry via composer once.

        Returns:
            Cleaned DashboardPlan (deterministic clean, or post-retry clean).
        """
        cleaned, drop_ratio = self._validate_and_count(plan)

        if drop_ratio <= 0.5:
            if drop_ratio > 0:
                logger.info("ReflexionValidator dropped %.0f%% sections (below threshold)", drop_ratio * 100)
            return cleaned

        logger.warning(
            "ReflexionValidator dropped %.0f%% sections — triggering LLM retry",
            drop_ratio * 100,
        )

        retry_context = self._build_retry_context(plan)
        retry_plan = composer.compose(
            classification,
            insights,
            retry_context=retry_context,
        )
        retry_cleaned, _ = self._validate_and_count(retry_plan)
        return retry_cleaned

    def _build_retry_context(self, original_plan: DashboardPlan) -> dict:
        """Build context dict describing what was dropped and what columns are available."""
        dropped_info = []
        for page in original_plan.pages:
            for section in page.sections:
                valid, reason = self._validate_section(section)
                if not valid:
                    dropped_info.append(f"  '{section.title}': {reason}")

        available = {}
        for table_id in set(list(self.raw_cols.keys()) + list(self.engineered_cols.keys())):
            available[table_id] = (
                self.raw_cols.get(table_id, [])
                + self.engineered_cols.get(table_id, [])
            )

        return {
            "dropped_sections": dropped_info,
            "available_columns": available,
        }
```

- [ ] **Step 4: Update `DashboardComposer.compose()` to accept `retry_context`**

In `core/dashboard_composer.py`, update `compose()`:

```python
    def compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
        retry_context: dict | None = None,
    ) -> DashboardPlan:
```

Update `_build_prompt()` to accept and append `retry_context`:

```python
    def _build_prompt(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
        retry_context: dict | None = None,
    ) -> str:
        ...
        # At the end, before the schema, append retry context if provided:
        if retry_context:
            prompt_lines.extend([
                "",
                "⚠ RETRY — sections précédentes rejetées (colonnes inexistantes) :",
            ])
            for line in retry_context.get("dropped_sections", []):
                prompt_lines.append(line)
            prompt_lines.extend([
                "",
                "Colonnes disponibles (utilisez UNIQUEMENT celles-ci) :",
            ])
            for table_id, cols in retry_context.get("available_columns", {}).items():
                prompt_lines.append(f"  {table_id}: {', '.join(cols)}")
```

Pass `retry_context` through in `compose()`:

```python
        prompt = self._build_prompt(classification, insights, feature_plan, retry_context)
```

- [ ] **Step 5: Run all reflexion tests**

```bash
pytest tests/test_reflexion.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/reflexion.py core/dashboard_composer.py tests/test_reflexion.py
git commit -m "feat: ReflexionValidator.validate() — LLM retry when >50% sections invalid"
```

---

## Task 11: Integrate `ReflexionValidator` into pipeline

**Files:**
- Modify: `core/pipeline.py`

- [ ] **Step 1: Wire validator in `PipelineOrchestrator.run()`**

In `core/pipeline.py`, add import:

```python
from core.reflexion import ReflexionValidator
```

After the `_compose` call in `run()`, add validation step:

```python
        # Agent 4.5: Reflexion Validation
        if result.dashboard_plan is not None and result.classification is not None:
            try:
                # Build column maps for validator
                raw_cols = profile.columns  # {actual_tableId: [col_id]}
                engineered_cols: dict[str, list[str]] = {}
                if result.feature_plan:
                    for f in result.feature_plan.features:
                        table_id = result.classification.table_mapping.get(f.table, f.table)
                        engineered_cols.setdefault(table_id, []).append(f.col_id)

                validator = ReflexionValidator(
                    raw_cols=raw_cols,
                    engineered_cols=engineered_cols,
                    table_mapping=result.classification.table_mapping,
                )
                result.dashboard_plan = validator.validate(
                    result.dashboard_plan,
                    result.classification,
                    result.insights,
                    self.composer,
                )
                debug_print("Agent 4.5 — ReflexionValidator", result.dashboard_plan, self.debug)
            except Exception as e:
                result.errors.append(f"ReflexionValidator failed: {e}")
```

- [ ] **Step 2: Smoke test**

```bash
source venv/bin/activate
python3 main.py --input samples/employees_rh.xlsx --dry-run --debug 2>&1 | grep -E "\[DEBUG|Pages|Dropped"
```

Expected: see `[DEBUG Agent 4.5 — ReflexionValidator]` block. No sections should be dropped for a valid plan.

- [ ] **Step 3: Commit**

```bash
git add core/pipeline.py
git commit -m "feat: wire ReflexionValidator into pipeline as Agent 4.5"
```

---

## Task 12: End-to-end validation

- [ ] **Step 1: Run full pipeline with debug**

```bash
source venv/bin/activate
python3 main.py --input samples/employees_rh.xlsx --debug 2>&1 | tee /tmp/pipeline_debug.txt
```

Expected output:
- `[DEBUG Agent 3.5 — FeatureEngineer]` — shows ≥1 formula column
- `[DEBUG Agent 4 — DashboardComposer]` — shows ≥3 pages, ≥3 charts
- `[DEBUG Agent 4.5 — ReflexionValidator]` — shows 0 sections dropped
- `[3b/4] Application des colonnes dérivées...` — shows applied cols
- `Pages créées : [...]` — 3+ pages

- [ ] **Step 2: Verify charts have data in Grist UI**

Open the URL printed at the end. Check:
- Dashboard Principal: at least one bar/line chart shows data (not empty)
- Liste des Employés: no "Cannot read properties of null" error
- Formulaire Employé: shows form fields

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: pipeline upgrade complete — chart fix, feature engineering, reflexion validator, debug mode"
```
