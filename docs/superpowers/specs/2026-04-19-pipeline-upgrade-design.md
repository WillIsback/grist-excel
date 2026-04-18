# Pipeline Upgrade — Design Spec

> Extends: `2026-04-18-data-to-dashboard-design.md`
> Inspired by: arXiv 2505.23695 — Reflexion loop, feature engineering, chart quality

## Problem

Current pipeline produces sparse dashboards with mostly empty charts:
- Bar/line charts render empty — Grist aggregation config missing
- No derived/computed metrics — insights like "Effectif Évalué vs Non Évalué" have no source columns
- `self_reflect()` was broken (string match) and was removed — no validation loop

## Goal

Three targeted fixes in priority order:
1. Fix chart rendering (bar, line, pie aggregation)
2. Add Agent 3.5 — FeatureEngineer (Grist formula columns for derived metrics)
3. Add Agent 4.5 — ReflexionValidator (deterministic validation + targeted LLM retry)

---

## Updated Pipeline

```
Excel
  ↓
Agent 1 — DataAnalyzer          (unchanged)
  ↓
Agent 2 — DomainClassifier      (unchanged)
  ↓
Agent 3 — InsightExtractor      (unchanged)
  ↓
Agent 3.5 — FeatureEngineer     ← NEW (LLM plans formula columns)
  ↓
Agent 4 — DashboardComposer     (prompt updated: may reference engineered columns)
  ↓
Agent 4.5 — ReflexionValidator  ← NEW (deterministic validation + optional LLM retry)
  ↓
GristImporter                   (unchanged — creates doc + raw tables)
  ↓
FeatureEngineer.apply()         ← NEW (writes formula cols to Grist)
  ↓
ArchetypeEngine                 (chart rendering fix applied)
```

Key invariant: feature engineering is **planned** by LLM before Grist doc creation, then **executed** after import. DashboardComposer can reference engineered columns in the plan without a second LLM pass.

---

## Fix 1 — Chart Rendering

**Root cause:** Grist bar/line charts need `options` JSON on `_grist_Views_section` and per-field `options` on `_grist_Views_section_field` to configure aggregation. Pie charts work without it (Grist defaults to grouping by first column).

**Changes to `archetypes/base.py` — `_add_chart_section`:**

1. Add `options` JSON to section record:
```python
options = json.dumps({
    "multiseries": False,
    "invertSeries": False,
    "isStacked": False,
})
```

2. Add per-field `options` JSON with aggregation:
```python
# x field (field 0): no aggregation
# y field (field 1+): aggregate per section.agg
{"aggregate": "count" | "sum" | "avg" | "max" | "min"}
```

3. Field position determines axis — x first, y second (already implemented).

4. `_add_chart_section` signature updated: accepts `agg: str | None` parameter passed from `GenericArchetype`.

**Investigation step required:** Before implementing, inspect `_grist_Views_section` and `_grist_Views_section_field` records of a hand-crafted working bar chart to confirm exact field names. This is the first implementation task.

---

## Fix 2 — Agent 3.5: FeatureEngineer

**New file:** `core/feature_engineer.py`

### Output Schema

```python
class FormulaColumn(BaseModel):
    table: str      # semantic role key from table_mapping (e.g. "employees")
    col_id: str     # Grist colId — ASCII, no spaces, no accents
    label: str      # human display label (French)
    type: str       # Grist type: Toggle, Int, Numeric, Text
    formula: str    # Grist Python formula using $ColName syntax

class FeaturePlan(BaseModel):
    features: list[FormulaColumn]  # 0–6 features
```

### LLM Prompt

Includes:
- Archetype + table_mapping
- Per-table column names (for valid `$ColName` references)
- Insight findings (to understand what derived metrics are needed)
- Grist formula syntax examples (4–5 canonical patterns)
- Instruction: generate only features that make insights chartable

### Grist Formula Examples provided in prompt

```python
# Count related records
len(Absences.lookupRecords(ID_Employe=$ID_Employe))

# Boolean existence check
bool(Evaluations.lookupOne(ID_Employe=$ID_Employe).ID_Employe)

# Numeric bucketing
"Haut" if $Salaire_Brute > 70000 else ("Moyen" if $Salaire_Brute > 45000 else "Bas")

# Average from related table
AVERAGE(Evaluations.lookupRecords(ID_Employe=$ID_Employe).Note) or 0

# Days since date
(TODAY() - $Date_Embauche).days if $Date_Embauche else 0
```

### Execution: `FeatureEngineer.apply(api, doc_id, plan, table_mapping)`

For each `FormulaColumn` in `FeaturePlan`:
1. Resolve `feature.table` (semantic role) → actual Grist tableId via `table_mapping`
2. `PATCH /api/docs/{docId}/tables/{tableId}/columns` with:
   ```json
   {"columns": [{"id": "col_id", "fields": {"type": "...", "label": "...", "formula": "...", "isFormula": true}}]}
   ```
3. Validation: `GET /api/docs/{docId}/tables/{tableId}/records?limit=1` — if Grist returns error data for the column, log warning and skip

### Integration in `pipeline.py` and `main.py`

`PipelineResult` gains `feature_plan: FeaturePlan | None`.

In `PipelineOrchestrator.run()`:
- After insight extraction: run FeatureEngineer LLM → `result.feature_plan`
- Pass engineered col_ids to DashboardComposer prompt

In `main.py` after `GristImporter`:
- Call `FeatureEngineer.apply(api, doc_id, result.feature_plan, result.classification.table_mapping)`

---

## Fix 3 — Agent 4.5: ReflexionValidator

**New file:** `core/reflexion.py`

### Constructor

```python
ReflexionValidator(
    raw_cols: dict[str, list[str]],        # {tableId: [colId, ...]} from DataProfile
    engineered_cols: dict[str, list[str]], # {tableId: [col_id, ...]} from FeaturePlan
    table_mapping: dict[str, str],         # semantic role → actual tableId
)
```

### Validation Logic (deterministic, no LLM)

```
For each page → each section:
  1. Resolve section.table (semantic role) → actual tableId
     - If unresolvable → drop section
  2. If widget == "chart":
     - Check section.x exists in (raw_cols[tableId] ∪ engineered_cols[tableId])
     - Check section.y exists in same set
     - If either missing → drop section, log (table, col, reason)
  3. If widget in (card_list, form, table):
     - Check tableId resolves → if not, drop
  4. If page has 0 surviving sections → drop page
```

### Outcome Logic

| Dropped ratio | Action |
|---|---|
| 0% | Return plan unchanged |
| 1–50% | Return cleaned plan silently |
| >50% | LLM retry (one attempt) |

### LLM Retry Prompt (targeted)

Sent to DashboardComposer with:
- Original insights
- Complete list of available columns per table (raw + engineered)
- Explicit dropped sections with reasons: `"chart 'X' dropped: column 'Y' not found in table 'Z'"`
- Instruction: generate only sections using listed columns

One retry — if still >50% invalid after retry, proceed with surviving sections.

### Integration in `pipeline.py`

`feature_plan_col_map` built from FeaturePlan by resolving semantic table role → actual tableId:

```python
feature_plan_col_map: dict[str, list[str]] = {}
for f in feature_plan.features:
    table_id = table_mapping.get(f.table, f.table)
    feature_plan_col_map.setdefault(table_id, []).append(f.col_id)
```

```python
# After DashboardComposer:
validator = ReflexionValidator(
    raw_cols=profile.columns,
    engineered_cols=feature_plan_col_map,
    table_mapping=classification.table_mapping,
)
result.dashboard_plan = validator.validate(
    result.dashboard_plan,
    result.classification,
    result.insights,
    composer,
)
```

---

## Files Changed / Created

| File | Change |
|---|---|
| `core/feature_engineer.py` | NEW — FeatureEngineer agent + FeaturePlan schema |
| `core/reflexion.py` | NEW — ReflexionValidator |
| `core/pipeline.py` | Add feature_plan to PipelineResult; wire Agent 3.5 + 4.5 |
| `core/dashboard_composer.py` | Update prompt to include engineered col_ids |
| `archetypes/base.py` | Fix `_add_chart_section` — options + agg per field |
| `archetypes/generic.py` | Pass `section.agg` to `_add_chart_section` |
| `main.py` | Call `FeatureEngineer.apply()` after GristImporter |

---

## Success Criteria

- Bar/line charts render with data (not empty) on `employees_rh.xlsx`
- At least 2 engineered columns created per run (HR archetype)
- DashboardComposer references engineered columns in ≥1 chart
- ReflexionValidator drops 0 sections on a valid plan
- Full pipeline runtime stays under 3 minutes on DGX Spark
