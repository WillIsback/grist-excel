# Interactive Checkpoints — Design Spec
_2026-04-19_

## Problem

Pipeline runs fully autonomously and assumes user intent. Dashboard output feels copy-pasted: same chart structure regardless of what the data actually contains or what the user wants to know. Pipeline never asks the question the user is actually trying to answer.

## Goal

Add two interactive checkpoints that let the user steer the pipeline using their domain expertise, while grounding every displayed insight in real statistics — not LLM-generated descriptions alone.

---

## Architecture

### New component: `core/checkpoint.py`

**Protocol:**
```python
class CheckpointHandler(Protocol):
    def on_classification(
        self, result: ClassificationResult, profile: DataProfile
    ) -> ClassificationFeedback: ...

    def on_insights(
        self, report: InsightReport, profile: DataProfile
    ) -> InsightFeedback: ...
```

**Feedback models:**
```python
class ClassificationFeedback(BaseModel):
    confirmed_archetype: ArchetypeLiteral
    user_intent: str   # "" = no intent, pipeline uses full DataProfile

class InsightFeedback(BaseModel):
    selected_indices: list[int]   # indices into InsightReport.insights
    custom_focus: str | None = None
```

**Concrete implementation:** `CLICheckpointHandler` — uses `input()`. Future `WebCheckpointHandler` uses HTTP polling. Same protocol, different transport.

### New component: `core/column_relevance_filter.py`

Agent 2.5 — lightweight vLLM call that trims DataProfile to intent-relevant columns before InsightExtractor runs.

**Input:** `user_intent: str` + flat list of `"Table.Column"` strings (no stats, cheap call)
**Output:** `dict[str, float]` — per-column relevance scores 0–1

**What "trimmed DataProfile" means:** only `profile.stats` entries are filtered (the large per-column stat dicts). `profile.columns`, `profile.sheets`, `profile.apparent_fk`, and `profile.summary_tables` remain intact — structural awareness is preserved. Soft-zone columns are iterated in descending score order when filling up to `RELEVANCE_MIN_COLUMNS`.

**Two-threshold hysteresis + table solidarity:**

| Score | Decision |
|-------|----------|
| `>= RELEVANCE_UPPER (0.6)` | Always included (hard in) |
| `<= RELEVANCE_LOWER (0.25)` | Always excluded (hard out) |
| `0.25 < score < 0.6` | Soft zone: include if same table as any hard-in column, or if total included count < `RELEVANCE_MIN_COLUMNS` |

**Why hysteresis:** A hard threshold would cut contextually essential columns. Example: user asks "why is turnover high" → `Date_Départ` scores 0.9 (hard in), `Département` scores 0.4 (soft zone) — table solidarity keeps `Département` because it shares the `Employés` table with `Date_Départ`. Without it, InsightExtractor cannot identify turnover by department.

**Tunable constants in `Settings`:**
```python
RELEVANCE_UPPER: float = 0.6
RELEVANCE_LOWER: float = 0.25
RELEVANCE_MIN_COLUMNS: int = 5
```

**Fallback:** if `user_intent` is empty, filter is skipped entirely — full DataProfile passes through. If filter returns fewer than `RELEVANCE_MIN_COLUMNS` after all rules, fall back to full DataProfile with a warning log.

---

## Updated Pipeline Sequence

```
Agent 1    DataAnalyzer          Excel → DataProfile
Agent 2    DomainClassifier      DataProfile → ClassificationResult
★          Checkpoint 1          user confirms archetype, enters intent
Agent 2.5  ColumnRelevanceFilter trims DataProfile to intent-relevant cols
Agent 3    InsightExtractor      trimmed profile + user_intent in prompt
★          Checkpoint 2          user selects insights (real stats shown)
Agent 3.5  FeatureEngineer       receives only selected insights
Agent 4    DashboardComposer     receives only selected insights
Agent 4.5  ReflexionValidator    unchanged
```

---

## Checkpoint 1 — Classification Confirmation

**Displayed to user:**
```
Archetype detected: HR (confidence: 0.87)
Tables mapped:
  employees → "Employés"   [45 rows, 12 cols]
  absences  → "Absences"   [230 rows, 6 cols]

Confirm archetype? [HR/DECISIONNEL/SUPPORT/STUDENT/SI/PROJECT/GENERIC] (enter=keep):
What do you want to analyze? (enter=skip): _
```

**Archetype override:** if user picks a different archetype, DomainClassifier reruns with an override hint injected into the prompt. Only classification reruns — not the full pipeline.

**Empty intent:** `user_intent = ""` → ColumnRelevanceFilter skipped, full DataProfile used, `user_intent` not injected into downstream prompts. Behavior identical to current pipeline.

---

## Checkpoint 2 — Insight Selection

**Each insight displayed with real stats from `profile.stats`**, not LLM text alone:

```
Insights found — select what matters to you:

[1] distribution — Employés.Département
    IT=45%  Finance=23%  Ops=20%  RH=12%
    Include? [Y/n]:

[2] trend — Absences.Date
    Peak: Jul–Aug (+340% vs avg)
    Include? [Y/n]:

Custom focus to add? (enter=skip): _
```

**Edge cases:**
- User deselects all: warn "No insights selected — dashboard will be minimal", allow proceed or redo
- `custom_focus` non-empty: appended to `user_intent` for FeatureEngineer and DashboardComposer prompts

---

## Changes Per File

| File | Change |
|------|--------|
| `core/pipeline.py` | Accept `checkpoint_handler: CheckpointHandler \| None = None`; call checkpoints; pass `user_intent` + filtered profile downstream |
| `core/insight_extractor.py` | Accept optional `user_intent: str`; inject into system prompt |
| `core/feature_engineer.py` | Accept optional `user_intent: str`; inject into prompt |
| `core/dashboard_composer.py` | Accept optional `user_intent: str`; inject into prompt |
| New: `core/checkpoint.py` | `CheckpointHandler` protocol + feedback models + `CLICheckpointHandler` |
| New: `core/column_relevance_filter.py` | Agent 2.5 — hysteresis relevance filter |
| `config.py` | Add `RELEVANCE_UPPER`, `RELEVANCE_LOWER`, `RELEVANCE_MIN_COLUMNS` |

No changes to: `data_analyzer`, `domain_classifier`, `reflexion`, `visual_intents`, `grist_api`, any archetype.

---

## Backward Compatibility

```python
# Existing — unchanged behavior
orchestrator = PipelineOrchestrator()
result = orchestrator.run_from_file("data.xlsx")

# New interactive mode
from core.checkpoint import CLICheckpointHandler
orchestrator = PipelineOrchestrator(checkpoint_handler=CLICheckpointHandler())
result = orchestrator.run_from_file("data.xlsx")
```

`checkpoint_handler=None` default — zero breakage to existing tests or callers.

---

## Future: WebCheckpointHandler

When web UI is added, implement `WebCheckpointHandler(CheckpointHandler)` that:
- POSTs classification result to a `/checkpoint/classification` endpoint
- Polls or awaits a `/checkpoint/classification/response` endpoint
- Same protocol, different transport — no changes to pipeline internals

---

## Out of Scope

- Saving/replaying user intent across sessions
- Multi-turn conversation beyond two checkpoints
- Embedding-based RAG (overkill for structured DataProfile)
