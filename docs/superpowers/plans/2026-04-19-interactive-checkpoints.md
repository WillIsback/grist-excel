# Interactive Checkpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two interactive checkpoints to the pipeline so users can confirm archetype, provide analysis intent, and select relevant insights — grounding the dashboard in their domain expertise rather than LLM assumptions.

**Architecture:** `CheckpointHandler` protocol with `CLICheckpointHandler` (CLI now, `WebCheckpointHandler` later — same interface). `ColumnRelevanceFilter` (Agent 2.5) trims `DataProfile.stats` to intent-relevant columns using two-threshold hysteresis + table solidarity. `user_intent` string threads through InsightExtractor, FeatureEngineer, and DashboardComposer prompts.

**Tech Stack:** Python 3.12, Pydantic v2, vLLM (local), pytest + unittest.mock, dataclasses.replace

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `core/checkpoint.py` | Protocol + feedback models + CLICheckpointHandler |
| Create | `core/column_relevance_filter.py` | Agent 2.5 — hysteresis column scoring |
| Create | `tests/test_checkpoint.py` | Tests for checkpoint models + CLICheckpointHandler |
| Create | `tests/test_column_relevance_filter.py` | Tests for relevance filter |
| Modify | `config.py` | Add RELEVANCE_UPPER, RELEVANCE_LOWER, RELEVANCE_MIN_COLUMNS |
| Modify | `core/insight_extractor.py` | Add user_intent param to extract() |
| Modify | `core/feature_engineer.py` | Add user_intent param to plan() |
| Modify | `core/dashboard_composer.py` | Add user_intent param to compose() |
| Modify | `core/pipeline.py` | Wire checkpoints + filter + user_intent |
| Modify | `tests/test_pipeline.py` | Backward-compat tests + checkpoint integration |

---

## Task 1: Config — Add Relevance Settings

**Files:**
- Modify: `config.py`
- Test: `tests/test_column_relevance_filter.py` (created here, extended in Task 4)

- [ ] **Step 1: Write failing test**

```python
# tests/test_column_relevance_filter.py
from config import Settings


def test_relevance_settings_defaults():
    s = Settings()
    assert s.RELEVANCE_UPPER == 0.6
    assert s.RELEVANCE_LOWER == 0.25
    assert s.RELEVANCE_MIN_COLUMNS == 5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python -m pytest tests/test_column_relevance_filter.py::test_relevance_settings_defaults -v
```
Expected: `FAILED` — `Settings` has no attribute `RELEVANCE_UPPER`

- [ ] **Step 3: Add settings to config.py**

In `config.py`, after the existing `STATS_TOP_VALUES` line, add:

```python
    # Column relevance filter (Agent 2.5)
    RELEVANCE_UPPER: float = 0.6
    RELEVANCE_LOWER: float = 0.25
    RELEVANCE_MIN_COLUMNS: int = 5
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/python -m pytest tests/test_column_relevance_filter.py::test_relevance_settings_defaults -v
```
Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_column_relevance_filter.py
git commit -m "feat: add relevance filter settings to config"
```

---

## Task 2: Checkpoint Models + Protocol

**Files:**
- Create: `core/checkpoint.py`
- Create: `tests/test_checkpoint.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_checkpoint.py
import pytest
from pydantic import ValidationError
from core.checkpoint import ClassificationFeedback, InsightFeedback


def test_classification_feedback_valid():
    fb = ClassificationFeedback(confirmed_archetype="HR", user_intent="pourquoi turnover élevé")
    assert fb.confirmed_archetype == "HR"
    assert fb.user_intent == "pourquoi turnover élevé"


def test_classification_feedback_empty_intent():
    fb = ClassificationFeedback(confirmed_archetype="GENERIC", user_intent="")
    assert fb.user_intent == ""


def test_classification_feedback_invalid_archetype():
    with pytest.raises(ValidationError):
        ClassificationFeedback(confirmed_archetype="INVALID", user_intent="test")


def test_insight_feedback_valid():
    fb = InsightFeedback(selected_indices=[0, 2, 4])
    assert fb.selected_indices == [0, 2, 4]
    assert fb.custom_focus is None


def test_insight_feedback_with_focus():
    fb = InsightFeedback(selected_indices=[1], custom_focus="analyse par ancienneté")
    assert fb.custom_focus == "analyse par ancienneté"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_checkpoint.py -v
```
Expected: `ERROR` — `cannot import name 'ClassificationFeedback' from 'core.checkpoint'`

- [ ] **Step 3: Create core/checkpoint.py with protocol + models**

```python
# core/checkpoint.py
"""Checkpoint handlers for interactive pipeline steering."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from core.domain_classifier import ArchetypeLiteral


class ClassificationFeedback(BaseModel):
    confirmed_archetype: ArchetypeLiteral
    user_intent: str  # empty string = no intent provided


class InsightFeedback(BaseModel):
    selected_indices: list[int]  # indices into InsightReport.insights
    custom_focus: str | None = None
```

Note: `CheckpointHandler` Protocol is defined in Task 3 alongside `CLICheckpointHandler` to avoid a circular import (Protocol references `DataProfile` and `InsightReport`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_checkpoint.py -v
```
Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/checkpoint.py tests/test_checkpoint.py
git commit -m "feat: add checkpoint feedback models"
```

---

## Task 3: CLICheckpointHandler

**Files:**
- Modify: `core/checkpoint.py`
- Modify: `tests/test_checkpoint.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_checkpoint.py`:

```python
from unittest.mock import patch, MagicMock
from core.checkpoint import CLICheckpointHandler, CheckpointHandler
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightEntry


def _make_profile():
    return DataProfile(
        sheets=["Employés"],
        columns={"Employés": ["ID", "Département", "Salaire"]},
        stats={
            "Employés.Département": {"non_null": 45, "null": 0, "unique": 4, "top": ["IT", "Finance", "Ops", "RH"]},
            "Employés.Salaire": {"non_null": 45, "null": 0, "unique": 45, "min": 30000.0, "max": 95000.0, "avg": 57000.0},
        },
        apparent_fk=[],
        markdown_summary="",
    )


def _make_classification():
    return ClassificationResult(
        archetype="HR",
        confidence=0.87,
        table_mapping={"employees": "Employés"},
        params={},
    )


def _make_insights():
    return InsightReport(insights=[
        InsightEntry(type="distribution", table="Employés", col="Département",
                     finding="IT concentre 45% des effectifs", priority=1),
        InsightEntry(type="outlier", table="Employés", col="Salaire",
                     finding="Salaires max élevés en Finance", priority=2),
    ])


def test_cli_handler_implements_protocol():
    handler = CLICheckpointHandler()
    assert isinstance(handler, CheckpointHandler)


def test_on_classification_keeps_archetype_on_enter(monkeypatch):
    handler = CLICheckpointHandler()
    monkeypatch.setattr("builtins.input", lambda _: "")
    fb = handler.on_classification(_make_classification(), _make_profile())
    assert fb.confirmed_archetype == "HR"
    assert fb.user_intent == ""


def test_on_classification_overrides_archetype(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["DECISIONNEL", "analyse des coûts par département"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_classification(_make_classification(), _make_profile())
    assert fb.confirmed_archetype == "DECISIONNEL"
    assert fb.user_intent == "analyse des coûts par département"


def test_on_classification_ignores_invalid_archetype(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["NOTVALID", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_classification(_make_classification(), _make_profile())
    assert fb.confirmed_archetype == "HR"  # falls back to original


def test_on_insights_selects_all_on_y(monkeypatch):
    handler = CLICheckpointHandler()
    monkeypatch.setattr("builtins.input", lambda _: "")  # enter = keep (default Y)
    fb = handler.on_insights(_make_insights(), _make_profile())
    assert fb.selected_indices == [0, 1]
    assert fb.custom_focus is None


def test_on_insights_deselects_on_n(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["n", "", ""])  # skip first, keep second, no custom focus
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_insights(_make_insights(), _make_profile())
    assert fb.selected_indices == [1]


def test_on_insights_captures_custom_focus(monkeypatch):
    handler = CLICheckpointHandler()
    inputs = iter(["", "", "analyse par ancienneté"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    fb = handler.on_insights(_make_insights(), _make_profile())
    assert fb.custom_focus == "analyse par ancienneté"


def test_format_stats_categorical():
    handler = CLICheckpointHandler()
    profile = _make_profile()
    result = handler._format_stats("Employés", "Département", profile)
    assert "IT" in result


def test_format_stats_numeric():
    handler = CLICheckpointHandler()
    profile = _make_profile()
    result = handler._format_stats("Employés", "Salaire", profile)
    assert "30000" in result and "95000" in result


def test_format_stats_missing_key():
    handler = CLICheckpointHandler()
    profile = _make_profile()
    result = handler._format_stats("Employés", "NonExistent", profile)
    assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_checkpoint.py -v
```
Expected: `FAILED` — `CLICheckpointHandler` and `CheckpointHandler` not yet defined

- [ ] **Step 3: Add CLICheckpointHandler + Protocol to core/checkpoint.py**

Replace the full contents of `core/checkpoint.py`:

```python
# core/checkpoint.py
"""Checkpoint handlers for interactive pipeline steering."""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel

from core.domain_classifier import ArchetypeLiteral

if TYPE_CHECKING:
    from core.data_analyzer import DataProfile
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport, InsightEntry


class ClassificationFeedback(BaseModel):
    confirmed_archetype: ArchetypeLiteral
    user_intent: str  # empty string = no intent provided


class InsightFeedback(BaseModel):
    selected_indices: list[int]  # indices into InsightReport.insights
    custom_focus: str | None = None


@runtime_checkable
class CheckpointHandler(Protocol):
    def on_classification(
        self, result: "ClassificationResult", profile: "DataProfile"
    ) -> ClassificationFeedback: ...

    def on_insights(
        self, report: "InsightReport", profile: "DataProfile"
    ) -> InsightFeedback: ...


ARCHETYPE_CHOICES = ["HR", "DECISIONNEL", "SUPPORT", "STUDENT", "SI", "PROJECT", "GENERIC"]


class CLICheckpointHandler:
    """Interactive CLI checkpoint handler using stdin/stdout."""

    def on_classification(
        self, result: "ClassificationResult", profile: "DataProfile"
    ) -> ClassificationFeedback:
        print(f"\nArchetype detected: {result.archetype} (confidence: {result.confidence:.2f})")
        print("Tables mapped:")
        for role, table in result.table_mapping.items():
            col_count = len(profile.columns.get(table, []))
            print(f"  {role} → \"{table}\"   [{col_count} cols]")

        choices_str = "/".join(ARCHETYPE_CHOICES)
        archetype_input = input(
            f"\nConfirm archetype? [{choices_str}] (enter=keep): "
        ).strip().upper()
        confirmed = (
            archetype_input
            if archetype_input in ARCHETYPE_CHOICES
            else result.archetype
        )

        user_intent = input("What do you want to analyze? (enter=skip): ").strip()

        return ClassificationFeedback(
            confirmed_archetype=confirmed,
            user_intent=user_intent,
        )

    def on_insights(
        self, report: "InsightReport", profile: "DataProfile"
    ) -> InsightFeedback:
        print("\nInsights found — select what matters to you:\n")
        selected: list[int] = []

        for i, entry in enumerate(report.insights):
            stats_line = self._format_stats(entry.table, entry.col, profile)
            print(f"[{i + 1}] {entry.type} — {entry.table}.{entry.col}")
            print(f"    {entry.finding}")
            if stats_line:
                print(f"    {stats_line}")
            answer = input("    Include? [Y/n]: ").strip().lower()
            if answer != "n":
                selected.append(i)

        custom_input = input("\nCustom focus to add? (enter=skip): ").strip()
        custom_focus = custom_input if custom_input else None

        if not selected:
            print("Warning: no insights selected — dashboard will be minimal.")

        return InsightFeedback(selected_indices=selected, custom_focus=custom_focus)

    def _format_stats(self, table: str, col: str, profile: "DataProfile") -> str:
        key = f"{table}.{col}"
        stats = profile.stats.get(key, {})
        if not stats:
            return ""
        if "top" in stats:
            return "Top: " + ", ".join(str(v) for v in stats["top"][:4])
        if "min" in stats:
            return f"min={stats['min']:.0f}  max={stats['max']:.0f}  avg={stats['avg']:.0f}"
        return ""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_checkpoint.py -v
```
Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/checkpoint.py tests/test_checkpoint.py
git commit -m "feat: add CLICheckpointHandler with stats display"
```

---

## Task 4: ColumnRelevanceFilter

**Files:**
- Create: `core/column_relevance_filter.py`
- Modify: `tests/test_column_relevance_filter.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_column_relevance_filter.py`:

```python
import dataclasses
from unittest.mock import patch, MagicMock
from core.column_relevance_filter import ColumnRelevanceFilter
from core.data_analyzer import DataProfile
from config import Settings


def _make_profile():
    return DataProfile(
        sheets=["Employés", "Absences"],
        columns={
            "Employés": ["Département", "Salaire", "Nom", "ID"],
            "Absences": ["Date", "Durée"],
        },
        stats={
            "Employés.Département": {"non_null": 45, "top": ["IT", "RH"]},
            "Employés.Salaire": {"non_null": 45, "min": 30000.0, "max": 95000.0, "avg": 57000.0},
            "Employés.Nom": {"non_null": 45, "top": ["Martin"]},
            "Employés.ID": {"non_null": 45, "unique": 45},
            "Absences.Date": {"non_null": 100, "top": ["2024-07"]},
            "Absences.Durée": {"non_null": 100, "min": 1.0, "max": 30.0, "avg": 5.0},
        },
        apparent_fk=[],
        markdown_summary="",
    )


def test_empty_intent_returns_original_profile():
    fltr = ColumnRelevanceFilter()
    profile = _make_profile()
    result = fltr.filter(profile, "")
    assert result is profile


def test_whitespace_intent_returns_original_profile():
    fltr = ColumnRelevanceFilter()
    profile = _make_profile()
    result = fltr.filter(profile, "   ")
    assert result is profile


def test_hard_in_columns_always_included():
    fltr = ColumnRelevanceFilter()
    profile = _make_profile()
    scores = {
        "Employés.Département": 0.9,
        "Employés.Salaire": 0.8,
        "Employés.Nom": 0.1,
        "Employés.ID": 0.05,
        "Absences.Date": 0.1,
        "Absences.Durée": 0.1,
    }
    included = fltr._apply_hysteresis(scores)
    assert "Employés.Département" in included
    assert "Employés.Salaire" in included


def test_hard_out_columns_excluded_unless_solidarity():
    fltr = ColumnRelevanceFilter()
    # Employés.Nom scores 0.1 (below LOWER=0.25), no hard-in in same table
    # Except Employés.Département is hard-in — so table solidarity applies!
    scores = {
        "Employés.Département": 0.9,   # hard-in
        "Employés.Nom": 0.1,            # hard-out BUT same table as hard-in
        "Absences.Date": 0.1,           # hard-out, no same-table hard-in
    }
    # hard-out is always excluded regardless of table solidarity
    included = fltr._apply_hysteresis(scores)
    assert "Absences.Date" not in included
    # hard-out columns below LOWER are excluded even if same table
    assert "Employés.Nom" not in included


def test_soft_zone_included_if_same_table_as_hard_in():
    fltr = ColumnRelevanceFilter()
    scores = {
        "Employés.Département": 0.9,   # hard-in
        "Employés.Salaire": 0.4,        # soft zone, same table → include
        "Absences.Date": 0.4,           # soft zone, no hard-in same table → depends on floor
    }
    included = fltr._apply_hysteresis(scores)
    assert "Employés.Salaire" in included


def test_floor_ensures_minimum_columns():
    s = Settings(RELEVANCE_MIN_COLUMNS=3, RELEVANCE_UPPER=0.6, RELEVANCE_LOWER=0.25)
    fltr = ColumnRelevanceFilter(s)
    scores = {
        "A.col1": 0.9,   # hard-in
        "B.col2": 0.4,   # soft, no solidarity
        "C.col3": 0.35,  # soft, no solidarity
    }
    included = fltr._apply_hysteresis(scores)
    assert len(included) >= 3


def test_filter_trims_stats_only():
    fltr = ColumnRelevanceFilter()
    profile = _make_profile()
    scores = {k: 0.9 for k in ["Employés.Département", "Employés.Salaire"]}
    scores.update({k: 0.1 for k in ["Employés.Nom", "Employés.ID", "Absences.Date", "Absences.Durée"]})

    with patch.object(fltr, "_score_columns", return_value=scores):
        result = fltr.filter(profile, "analyse des salaires par département")

    # columns list is preserved
    assert result.columns == profile.columns
    assert result.sheets == profile.sheets
    assert result.apparent_fk == profile.apparent_fk
    # stats is trimmed
    assert "Employés.Département" in result.stats
    assert "Employés.Salaire" in result.stats


def test_filter_falls_back_on_too_few_columns():
    s = Settings(RELEVANCE_MIN_COLUMNS=10)  # impossible to satisfy
    fltr = ColumnRelevanceFilter(s)
    profile = _make_profile()
    all_low = {k: 0.1 for k in profile.stats}

    with patch.object(fltr, "_score_columns", return_value=all_low):
        result = fltr.filter(profile, "intent")

    assert result is profile  # fell back to full profile
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_column_relevance_filter.py -v
```
Expected: `ERROR` — `cannot import name 'ColumnRelevanceFilter'`

- [ ] **Step 3: Create core/column_relevance_filter.py**

```python
# core/column_relevance_filter.py
"""Agent 2.5 — Column Relevance Filter.

Trims DataProfile.stats to intent-relevant columns using two-threshold
hysteresis + table solidarity. Only profile.stats is filtered; structural
fields (columns, sheets, apparent_fk, summary_tables) are preserved.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import requests
from typing import Any

from pydantic import BaseModel

from config import Settings
from core.data_analyzer import DataProfile

logger = logging.getLogger(__name__)


class _ColumnScores(BaseModel):
    scores: dict[str, float]  # "Table.Column" -> 0.0-1.0


class ColumnRelevanceFilter:
    """Filters DataProfile.stats to columns relevant to user_intent."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def filter(self, profile: DataProfile, user_intent: str) -> DataProfile:
        """Return DataProfile with stats trimmed to intent-relevant columns.

        Returns original profile unchanged if user_intent is empty or if
        the filter result would have fewer than RELEVANCE_MIN_COLUMNS columns.
        """
        if not user_intent.strip():
            return profile

        all_keys = list(profile.stats.keys())
        if not all_keys:
            return profile

        scores = self._score_columns(all_keys, user_intent)
        included = self._apply_hysteresis(scores)

        if len(included) < self.settings.RELEVANCE_MIN_COLUMNS:
            logger.warning(
                "ColumnRelevanceFilter: only %d columns passed — falling back to full profile",
                len(included),
            )
            return profile

        trimmed_stats = {k: v for k, v in profile.stats.items() if k in included}
        return dataclasses.replace(profile, stats=trimmed_stats)

    def _score_columns(self, column_keys: list[str], user_intent: str) -> dict[str, float]:
        """Call vLLM to score each column's relevance to user_intent (0.0–1.0)."""
        col_list = "\n".join(f"  - {k}" for k in column_keys)
        prompt = (
            f"Question utilisateur : \"{user_intent}\"\n\n"
            f"Évaluez la pertinence de chaque colonne (0.0=non pertinent, 1.0=très pertinent) "
            f"pour répondre à cette question.\n\n"
            f"Colonnes à évaluer :\n{col_list}\n\n"
            f"Répondez UNIQUEMENT en JSON avec exactement les clés fournies :\n"
            f'{{"scores": {{"Table.Colonne": 0.0, ...}}}}'
        )
        messages = [
            {
                "role": "system",
                "content": "Vous êtes un analyste de pertinence de données. Répondez UNIQUEMENT en JSON valide.",
            },
            {"role": "user", "content": prompt},
        ]
        schema = _ColumnScores.model_json_schema()
        url = f"{self.settings.VLLM_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.1,
            "chat_template_kwargs": {"enable_thinking": False},
            "extra_body": {"guided_json": schema},
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content", "")
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            content = json_match.group(0)
        raw_scores: dict[str, float] = json.loads(content).get("scores", {})
        return {k: float(raw_scores.get(k, 0.5)) for k in column_keys}

    def _apply_hysteresis(self, scores: dict[str, float]) -> set[str]:
        """Two-threshold hysteresis + table solidarity.

        Hard-in  (>= RELEVANCE_UPPER): always included.
        Hard-out (<= RELEVANCE_LOWER): always excluded.
        Soft zone (between): included if same table as any hard-in column,
        then filled by score descending until RELEVANCE_MIN_COLUMNS floor.
        """
        upper = self.settings.RELEVANCE_UPPER
        lower = self.settings.RELEVANCE_LOWER
        min_cols = self.settings.RELEVANCE_MIN_COLUMNS

        hard_in: set[str] = {k for k, s in scores.items() if s >= upper}
        hard_in_tables: set[str] = {k.split(".")[0] for k in hard_in}

        soft_zone: list[tuple[str, float]] = sorted(
            [(k, s) for k, s in scores.items() if lower < s < upper],
            key=lambda x: x[1],
            reverse=True,
        )

        included: set[str] = set(hard_in)

        # Table solidarity pass
        for key, _ in soft_zone:
            table = key.split(".")[0]
            if table in hard_in_tables:
                included.add(key)

        # Floor pass — fill from soft zone by score until minimum reached
        for key, _ in soft_zone:
            if len(included) >= min_cols:
                break
            included.add(key)

        return included
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_column_relevance_filter.py -v
```
Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/column_relevance_filter.py tests/test_column_relevance_filter.py
git commit -m "feat: add ColumnRelevanceFilter with hysteresis and table solidarity"
```

---

## Task 5: InsightExtractor — user_intent

**Files:**
- Modify: `core/insight_extractor.py`
- Modify: `tests/test_insight_extractor.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_insight_extractor.py`:

```python
from unittest.mock import patch


def test_extract_injects_user_intent_into_system_prompt():
    from core.insight_extractor import InsightExtractor
    from core.data_analyzer import DataProfile
    from core.domain_classifier import ClassificationResult
    import json

    profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
    classification = ClassificationResult(
        archetype="HR", confidence=0.9,
        table_mapping={"employees": "Employes"}, params={},
    )
    extractor = InsightExtractor()
    mock_return = {
        "insights": [{"type": "distribution", "table": "Employes", "col": "Departement",
                      "finding": "test", "priority": 1}]
    }

    captured_messages = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured_messages.extend(messages)
        return mock_return

    with patch.object(extractor, "_call_llm", side_effect=fake_call_llm):
        extractor.extract(profile, classification, user_intent="pourquoi le turnover est élevé")

    system_msg = captured_messages[0]["content"]
    assert "pourquoi le turnover est élevé" in system_msg


def test_extract_no_intent_unchanged_behavior():
    from core.insight_extractor import InsightExtractor
    from core.data_analyzer import DataProfile
    from core.domain_classifier import ClassificationResult

    profile = DataProfile.from_json(SAMPLE_PROFILE_JSON)
    classification = ClassificationResult(
        archetype="HR", confidence=0.9,
        table_mapping={"employees": "Employes"}, params={},
    )
    extractor = InsightExtractor()
    mock_return = {
        "insights": [{"type": "kpi", "table": "Employes", "col": "Salaire",
                      "finding": "test", "priority": 1}]
    }
    captured_messages = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured_messages.extend(messages)
        return mock_return

    with patch.object(extractor, "_call_llm", side_effect=fake_call_llm):
        extractor.extract(profile, classification, user_intent=None)

    system_msg = captured_messages[0]["content"]
    assert "FOCUS" not in system_msg
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_insight_extractor.py::test_extract_injects_user_intent_into_system_prompt tests/test_insight_extractor.py::test_extract_no_intent_unchanged_behavior -v
```
Expected: `FAILED` — `extract()` doesn't accept `user_intent`

- [ ] **Step 3: Update InsightExtractor.extract() in core/insight_extractor.py**

Change the `extract` method signature and system prompt:

```python
def extract(
    self,
    profile: DataProfile,
    classification: ClassificationResult,
    user_intent: str | None = None,
) -> InsightReport:
    prompt = self._build_prompt(profile, classification)
    system_content = (
        "Vous êtes un analyste de données métier. "
        "Extrayez maximum 5 insights pertinents du profil de données. "
        "Pour chaque insight, indiquez le type, la table, la colonne concernée, "
        "et un résumé du résultat en français. "
        "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
    )
    if user_intent:
        system_content += (
            f"\n\nFOCUS EXCLUSIF sur la question de l'utilisateur : {user_intent}"
            "\nIgnorez les insights non liés à cette question."
        )
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    return InsightReport(**self._call_llm(messages))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_insight_extractor.py -v
```
Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/insight_extractor.py tests/test_insight_extractor.py
git commit -m "feat: InsightExtractor accepts user_intent for focused extraction"
```

---

## Task 6: FeatureEngineer — user_intent

**Files:**
- Modify: `core/feature_engineer.py`
- Modify: `tests/test_feature_engineer.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_feature_engineer.py`:

```python
def test_plan_injects_user_intent_into_prompt():
    eng = FeatureEngineer()
    captured = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured.extend(messages)
        return {"features": []}

    with patch.object(eng, "_call_llm", side_effect=fake_call_llm):
        eng.plan(_make_profile(), _make_classification(), _make_insights(),
                 user_intent="réduire le turnover")

    user_msg = captured[1]["content"]
    assert "réduire le turnover" in user_msg


def test_plan_without_intent_unchanged():
    eng = FeatureEngineer()
    captured = []

    def fake_call_llm(messages, schema=None, _retry=False):
        captured.extend(messages)
        return {"features": []}

    with patch.object(eng, "_call_llm", side_effect=fake_call_llm):
        eng.plan(_make_profile(), _make_classification(), _make_insights(),
                 user_intent=None)

    user_msg = captured[1]["content"]
    assert "Objectif" not in user_msg
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_feature_engineer.py::test_plan_injects_user_intent_into_prompt tests/test_feature_engineer.py::test_plan_without_intent_unchanged -v
```
Expected: `FAILED`

- [ ] **Step 3: Update FeatureEngineer.plan() in core/feature_engineer.py**

Change `plan()` to accept and inject `user_intent`:

```python
def plan(
    self,
    profile: DataProfile,
    classification: ClassificationResult,
    insights: InsightReport,
    user_intent: str | None = None,
) -> FeaturePlan:
    prompt = self._build_prompt(profile, classification, insights)
    if user_intent:
        prompt += (
            f"\n\nObjectif utilisateur : {user_intent}\n"
            "Prioriser les colonnes dérivées qui aident à répondre à cette question."
        )
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_feature_engineer.py -v
```
Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/feature_engineer.py tests/test_feature_engineer.py
git commit -m "feat: FeatureEngineer accepts user_intent for focused feature planning"
```

---

## Task 7: DashboardComposer — user_intent

**Files:**
- Modify: `core/dashboard_composer.py`
- Modify: `tests/test_dashboard_composer.py`

- [ ] **Step 1: Write failing test**

First check the existing test file to find the right helper functions to reuse:

```bash
head -60 tests/test_dashboard_composer.py
```

Then append to `tests/test_dashboard_composer.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_dashboard_composer.py::test_compose_injects_user_intent_into_system_prompt tests/test_dashboard_composer.py::test_compose_no_intent_unchanged -v
```
Expected: `FAILED`

- [ ] **Step 3: Update DashboardComposer.compose() in core/dashboard_composer.py**

Add `user_intent` parameter and inject into system content. Find the `compose` method and update:

```python
def compose(
    self,
    classification: ClassificationResult,
    insights: InsightReport,
    feature_plan: "FeaturePlan | None" = None,
    retry_context: dict | None = None,
    raw_cols: dict | None = None,
    stats: dict | None = None,
    summary_tables: list[dict[str, Any]] | None = None,
    visual_intents: "VisualIntentPlan | None" = None,
    user_intent: str | None = None,
) -> DashboardPlan:
    """Compose a dashboard plan."""
    prompt = self._build_prompt(classification, insights, feature_plan, retry_context,
                                raw_cols=raw_cols, stats=stats,
                                summary_tables=summary_tables,
                                visual_intents=visual_intents)
    system_content = (
        "Vous êtes un architecte de dashboards Grist. "
        "Composez un plan de dashboard basé sur les insights métier fournis. "
        "Mappez chaque insight à un widget de chart. "
        "Ajoutez aussi une page formulaire pour la table principale. "
        "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
    )
    if user_intent:
        system_content += (
            f"\n\nObjectif utilisateur : {user_intent}\n"
            "Prioriser les widgets qui répondent directement à cette question."
        )
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    raw_data = self._call_llm(messages)
    # Filter out invalid chart sections before Pydantic validation
```

The full new `compose()` method body after `messages = [...]`:

```python
    raw_data = self._call_llm(messages)
    # Filter out invalid chart sections before Pydantic validation
    pages_data = raw_data.get("pages", [])
    for page in pages_data:
        valid_sections = []
        for section in page.get("sections", []):
            if section.get("widget") == "chart":
                if not section.get("chart_type"):
                    continue
                if section.get("chart_type") == "line":
                    if not section.get("x") or not section.get("y"):
                        continue
            valid_sections.append(section)
        page["sections"] = valid_sections
    raw_data["pages"] = pages_data
    plan = DashboardPlan(**raw_data)
    return self._append_summary_sections(plan, summary_tables, visual_intents)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_dashboard_composer.py -v
```
Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/dashboard_composer.py tests/test_dashboard_composer.py
git commit -m "feat: DashboardComposer accepts user_intent for focused layout"
```

---

## Task 8: Wire Checkpoints into PipelineOrchestrator

**Files:**
- Modify: `core/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_pipeline.py`:

```python
from unittest.mock import MagicMock, patch, call
from core.checkpoint import ClassificationFeedback, InsightFeedback
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport, InsightEntry


def _mock_classification():
    return ClassificationResult(
        archetype="HR", confidence=0.9,
        table_mapping={"employees": "Employes"}, params={},
    )


def _mock_insights():
    return InsightReport(insights=[
        InsightEntry(type="distribution", table="Employes", col="Departement",
                     finding="IT domine", priority=1),
        InsightEntry(type="kpi", table="Employes", col="Salaire",
                     finding="salaire élevé", priority=2),
    ])


class TestPipelineCheckpoints:

    def test_no_handler_runs_without_checkpoint(self):
        """Default pipeline (no handler) runs unchanged."""
        orchestrator = PipelineOrchestrator()
        profile = _mock_profile()
        with patch.object(orchestrator, "_classify", return_value=_mock_classification()), \
             patch.object(orchestrator, "_extract", return_value=_mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            result = orchestrator.run(profile)
        assert result.errors == []

    def test_handler_called_after_classification(self):
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="HR", user_intent=""
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[0, 1])

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()

        with patch.object(orchestrator, "_classify", return_value=_mock_classification()), \
             patch.object(orchestrator, "_extract", return_value=_mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            orchestrator.run(profile)

        handler.on_classification.assert_called_once()
        handler.on_insights.assert_called_once()

    def test_archetype_override_applied(self):
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="DECISIONNEL", user_intent=""
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[0])

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()
        result_classification = _mock_classification()

        with patch.object(orchestrator, "_classify", return_value=result_classification), \
             patch.object(orchestrator, "_extract", return_value=_mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            result = orchestrator.run(profile)

        assert result.classification.archetype == "DECISIONNEL"

    def test_insight_selection_filters_report(self):
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="HR", user_intent=""
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[1])  # only index 1

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()
        captured_insights = []

        def fake_plan(p, c, insights, user_intent=None):
            captured_insights.append(insights)
            return MagicMock(features=[])

        with patch.object(orchestrator, "_classify", return_value=_mock_classification()), \
             patch.object(orchestrator, "_extract", return_value=_mock_insights()), \
             patch.object(orchestrator.feature_engineer, "plan", side_effect=fake_plan), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            orchestrator.run(profile)

        assert len(captured_insights[0].insights) == 1
        assert captured_insights[0].insights[0].col == "Salaire"  # index 1

    def test_user_intent_passed_to_extract(self):
        handler = MagicMock()
        handler.on_classification.return_value = ClassificationFeedback(
            confirmed_archetype="HR", user_intent="analyser le turnover"
        )
        handler.on_insights.return_value = InsightFeedback(selected_indices=[0])

        orchestrator = PipelineOrchestrator(checkpoint_handler=handler)
        profile = _mock_profile()
        captured_kwargs = {}

        def fake_extract(p, c, user_intent=None):
            captured_kwargs["user_intent"] = user_intent
            return _mock_insights()

        with patch.object(orchestrator, "_classify", return_value=_mock_classification()), \
             patch.object(orchestrator, "_extract", side_effect=fake_extract), \
             patch.object(orchestrator.feature_engineer, "plan", return_value=MagicMock(features=[])), \
             patch.object(orchestrator, "_compose", return_value=MagicMock(pages=[])), \
             patch.object(orchestrator, "_resolve_visual_intents", return_value=MagicMock(intents=[])):
            orchestrator.run(profile)

        assert captured_kwargs["user_intent"] == "analyser le turnover"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_pipeline.py::TestPipelineCheckpoints -v
```
Expected: `FAILED` — `PipelineOrchestrator.__init__` doesn't accept `checkpoint_handler`

- [ ] **Step 3: Update core/pipeline.py**

Add imports at the top of `core/pipeline.py` (after existing imports):

```python
from core.checkpoint import CheckpointHandler, ClassificationFeedback, InsightFeedback
from core.column_relevance_filter import ColumnRelevanceFilter
```

Update `__init__`:

```python
def __init__(self, settings: Settings | None = None, checkpoint_handler: "CheckpointHandler | None" = None):
    self.settings = settings or Settings()
    self.debug = self.settings.DEBUG
    self.data_analyzer = DataAnalyzer(settings)
    self.classifier = DomainClassifier(settings)
    self.insight_extractor = InsightExtractor(settings)
    self.composer = DashboardComposer(settings)
    self.feature_engineer = FeatureEngineer(settings)
    self.visual_intent_resolver = VisualIntentResolver()
    self.checkpoint_handler = checkpoint_handler
    self.relevance_filter = ColumnRelevanceFilter(settings)
```

Update `_extract` signature to forward `user_intent`:

```python
def _extract(
    self,
    profile: DataProfile,
    classification: ClassificationResult,
    user_intent: str | None = None,
) -> InsightReport:
    return self.insight_extractor.extract(profile, classification, user_intent=user_intent)
```

Update `_compose` signature to forward `user_intent`:

```python
def _compose(
    self,
    classification: ClassificationResult,
    insights: InsightReport,
    feature_plan: "FeaturePlan | None" = None,
    raw_cols: dict | None = None,
    stats: dict | None = None,
    summary_tables: list[dict[str, Any]] | None = None,
    visual_intents: VisualIntentPlan | None = None,
    user_intent: str | None = None,
) -> DashboardPlan:
    return self.composer.compose(
        classification, insights, feature_plan,
        raw_cols=raw_cols, stats=stats,
        summary_tables=summary_tables,
        visual_intents=visual_intents,
        user_intent=user_intent,
    )
```

Replace the full `run()` method:

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

    # ★ Checkpoint 1: classification confirmation + user intent
    user_intent: str = ""
    if self.checkpoint_handler and result.classification is not None:
        try:
            feedback = self.checkpoint_handler.on_classification(result.classification, profile)
            if feedback.confirmed_archetype != result.classification.archetype:
                result.classification = ClassificationResult(
                    archetype=feedback.confirmed_archetype,
                    confidence=result.classification.confidence,
                    table_mapping=result.classification.table_mapping,
                    params=result.classification.params,
                )
            user_intent = feedback.user_intent
        except Exception as e:
            result.errors.append(f"Checkpoint 1 failed: {e}")

    # Agent 2.5: column relevance filter (only when intent provided)
    active_profile = profile
    if user_intent and result.classification is not None:
        try:
            active_profile = self.relevance_filter.filter(profile, user_intent)
            debug_print("Agent 2.5 — ColumnRelevanceFilter", active_profile, self.debug)
        except Exception as e:
            result.errors.append(f"ColumnRelevanceFilter failed: {e}")

    if result.classification is not None:
        try:
            result.insights = self._extract(
                active_profile, result.classification,
                user_intent=user_intent or None,
            )
            debug_print("Agent 3 — InsightExtractor", result.insights, self.debug)
        except Exception as e:
            result.errors.append(f"InsightExtractor failed: {e}")

    # ★ Checkpoint 2: insight selection
    if self.checkpoint_handler and result.insights is not None:
        try:
            feedback2 = self.checkpoint_handler.on_insights(result.insights, profile)
            if feedback2.selected_indices is not None:
                all_insights = result.insights.insights
                selected = [
                    all_insights[i]
                    for i in feedback2.selected_indices
                    if i < len(all_insights)
                ]
                if selected:
                    result.insights = InsightReport(insights=selected)
            if feedback2.custom_focus:
                user_intent = (
                    f"{user_intent} {feedback2.custom_focus}".strip()
                    if user_intent
                    else feedback2.custom_focus
                )
        except Exception as e:
            result.errors.append(f"Checkpoint 2 failed: {e}")

    # Agent 3.5: Feature Engineering
    if result.classification is not None and result.insights is not None:
        try:
            result.feature_plan = self.feature_engineer.plan(
                profile, result.classification, result.insights,
                user_intent=user_intent or None,
            )
            debug_print("Agent 3.5 — FeatureEngineer", result.feature_plan, self.debug)
        except Exception as e:
            result.errors.append(f"FeatureEngineer failed: {e}")
            result.feature_plan = FeaturePlan(features=[])

    if result.classification is not None and result.insights is not None:
        try:
            result.visual_intents = self._resolve_visual_intents(
                profile, result.classification, result.insights,
            )
            debug_print("VisualIntentResolver", result.visual_intents, self.debug)
        except Exception as e:
            result.errors.append(f"VisualIntentResolver failed: {e}")

    if result.classification is not None and result.insights is not None:
        try:
            result.dashboard_plan = self._compose(
                result.classification, result.insights, result.feature_plan,
                raw_cols=profile.columns, stats=profile.stats,
                summary_tables=profile.summary_tables,
                visual_intents=result.visual_intents,
                user_intent=user_intent or None,
            )
            debug_print("Agent 4 — DashboardComposer", result.dashboard_plan, self.debug)
        except Exception as e:
            result.errors.append(f"DashboardComposer failed: {e}")

    # Agent 4.5: Reflexion Validation
    if result.dashboard_plan is not None and result.classification is not None:
        try:
            raw_cols = profile.columns
            engineered_cols: dict[str, list[str]] = {}
            if result.feature_plan:
                for f in result.feature_plan.features:
                    table_id = result.classification.table_mapping.get(f.table, f.table)
                    engineered_cols.setdefault(table_id, []).append(f.col_id)

            validator = ReflexionValidator(
                raw_cols=raw_cols,
                engineered_cols=engineered_cols,
                table_mapping=result.classification.table_mapping,
                summary_tables=profile.summary_tables,
                visual_intents=result.visual_intents,
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

    return result
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_grist_api.py --ignore=tests/test_grist_importer.py -x
```
Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/pipeline.py tests/test_pipeline.py
git commit -m "feat: wire CheckpointHandler and ColumnRelevanceFilter into PipelineOrchestrator"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/test_grist_api.py --ignore=tests/test_grist_importer.py -v
```
Expected: all tests pass, no regressions

- [ ] **Smoke test backward compatibility**

```python
# Verify existing usage still works with no handler
from core.pipeline import PipelineOrchestrator
o = PipelineOrchestrator()
assert o.checkpoint_handler is None
print("Backward compat OK")
```

Run: `.venv/bin/python -c "from core.pipeline import PipelineOrchestrator; o = PipelineOrchestrator(); assert o.checkpoint_handler is None; print('OK')"`

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: interactive checkpoints — user-steered pipeline (Agent 2.5 + Checkpoint 1&2)"
```
