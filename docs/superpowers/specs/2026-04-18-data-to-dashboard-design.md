# Data-to-Dashboard — Design Spec

> Inspired by: "Data-to-Dashboard" (arXiv 2505.23695) — multi-agent LLM pipeline for insight-driven dashboard generation.

## Problem

The current tool adds formula columns to an existing Grist document. This requires the user to already know Grist, manually import their Excel file, and interpret raw API suggestions. Non-expert users get no actionable result.

## Goal

A non-expert user provides an Excel file. The tool produces a fully configured Grist document — pages, charts, card views, forms — driven by business insights extracted from the data. Zero Grist knowledge required.

## New CLI

```bash
python main.py --input employees_rh.xlsx
python main.py --input sales_2024.xlsx --dry-run
```

`--doc-name` / `--doc-id` flags are removed. The Excel file is the single entry point.

---

## Pipeline — 4 Specialized Agents

```
Excel file
  │
  ▼
[Agent 1 — Data Analyzer]
  markitdown(xlsx) → Markdown
  Python stats (min/max/avg/unique/top_values per column)
  Detect apparent foreign keys between sheets
  → DataProfile JSON

  │
  ▼
[Agent 2 — Domain Classifier]      (guided_json + guided_choice via vLLM)
  Input : DataProfile + exact name lists (sheets / columns)
  LLM selects ONLY from provided lists — no free-text name generation
  → ClassificationResult JSON
  If confidence < 0.6 → archetype = GENERIC

  │
  ▼
[Agent 3 — Insight Extractor]      (guided_json via vLLM)
  Input : DataProfile + ClassificationResult
  Multi-perspective analysis : temporal / distribution / outlier / relation / KPI
  Max 5 insights, sorted by business relevance
  → InsightReport JSON

  │
  ▼
[Agent 4 — Dashboard Composer]     (guided_json via vLLM)
  Input : ClassificationResult + InsightReport
  Selects archetype template
  Maps each insight to a widget (chart type, axes, title = insight finding)
  Self-reflection pass : validates every widget is justified by an insight
  → DashboardPlan JSON

  │
  ▼
[Grist Importer]
  POST /api/docs (binary xlsx) → docId

  │
  ▼
[Archetype Engine]
  Resolves real tableRefs via GET /api/docs/{docId}/tables
  POST /api/docs/{docId}/apply per page (pre-tested action sequences)
  → Augmented Grist document
```

---

## Inter-Agent JSON Schemas

### DataProfile (Agent 1 output)

```json
{
  "sheets": ["Employes", "Absences"],
  "columns": {
    "Employes": ["Nom", "Departement", "Salaire_Brute", "Date_Embauche"],
    "Absences": ["ID_Employe", "Date_Debut", "Duree_Jours", "Type"]
  },
  "stats": {
    "Employes.Departement": {
      "non_null": 50, "unique": 6,
      "top": ["RH", "IT", "Finance"]
    },
    "Employes.Salaire_Brute": {
      "non_null": 50, "min": 28000, "max": 95000, "avg": 51200
    }
  },
  "apparent_fk": [
    {"from": "Absences.ID_Employe", "to": "Employes.ID"}
  ]
}
```

### ClassificationResult (Agent 2 output)

```json
{
  "archetype": "HR",
  "confidence": 0.91,
  "table_mapping": {
    "employees": "Employes",
    "absences": "Absences"
  },
  "params": {
    "name_col": "Nom",
    "department_col": "Departement",
    "date_col": "Date_Debut",
    "numeric_col": "Salaire_Brute"
  }
}
```

**Constraint:** `archetype` is a `guided_choice` — values: `HR | DECISIONNEL | SUPPORT | STUDENT | SI | PROJECT | GENERIC`. All values in `table_mapping` and `params` are selected from the lists provided in the prompt — never generated freely by the LLM.

### InsightReport (Agent 3 output)

```json
{
  "insights": [
    {
      "type": "distribution",
      "table": "Employes",
      "col": "Departement",
      "finding": "IT et Finance concentrent 68% des effectifs",
      "priority": 1
    },
    {
      "type": "trend",
      "table": "Absences",
      "col": "Date_Debut",
      "finding": "Pic d'absences en janvier (+40% vs moyenne)",
      "priority": 2
    },
    {
      "type": "outlier",
      "table": "Employes",
      "col": "Salaire_Brute",
      "finding": "8 salaires > 80k€, tous en IT senior",
      "priority": 3
    }
  ]
}
```

Insight types: `distribution | trend | outlier | relation | kpi`. Max 5 insights. All `table` and `col` values selected from DataProfile lists.

### DashboardPlan (Agent 4 output)

```json
{
  "pages": [
    {
      "name": "Dashboard RH",
      "sections": [
        {
          "widget": "chart",
          "chart_type": "bar",
          "table": "Employes",
          "x": "Departement",
          "y": "Nom",
          "agg": "count",
          "title": "IT et Finance concentrent 68% des effectifs"
        },
        {
          "widget": "chart",
          "chart_type": "line",
          "table": "Absences",
          "x": "Date_Debut",
          "y": "Duree_Jours",
          "agg": "sum",
          "title": "Pic d'absences en janvier (+40%)"
        }
      ]
    },
    {
      "name": "Employés",
      "sections": [
        {"widget": "card_list", "table": "Employes", "title": "Annuaire"}
      ]
    },
    {
      "name": "Saisie",
      "sections": [
        {"widget": "form", "table": "Employes", "title": "Nouvel employé"}
      ]
    }
  ]
}
```

Widget types: `chart | table | card_list | card | form`. Chart types: `bar | line | pie | area`.

---

## Archetype Catalog

Each archetype declares: expected semantic roles (`table_mapping` keys), required `params`, and a base page set. Optional tables (`?`) trigger adapted templates if absent.

| Archetype | Semantic Roles | Pages Created |
|---|---|---|
| **HR** | `employees`, `absences`?, `evaluations`? | Dashboard RH, Absences calendar, Employee form |
| **DECISIONNEL** | `main` (1+ tables) | Dashboard analytics, Raw data table |
| **SUPPORT** | `tickets`, `customers`?, `agents`? | Ticket card list by status, Support dashboard, Ticket form |
| **STUDENT** | `students`, `grades`?, `courses`? | Student card list, Grade summary, Dashboard |
| **SI** | `assets`, `users`?, `incidents`? | Inventory table, SI dashboard, Incident form |
| **PROJECT** | `tasks`, `team`?, `milestones`? | Task card list by status, Project dashboard, Task form |
| **GENERIC** | any | Main table, Basic dashboard (if numeric+category detected), Entry form |

---

## Module Structure

### New modules

| File | Responsibility |
|---|---|
| `core/data_analyzer.py` | Agent 1: markitdown + stats → DataProfile |
| `core/domain_classifier.py` | Agent 2: DataProfile → ClassificationResult (guided_json) |
| `core/insight_extractor.py` | Agent 3: DataProfile + Classification → InsightReport (guided_json) |
| `core/dashboard_composer.py` | Agent 4: Classification + Insights → DashboardPlan (guided_json + self-reflection) |
| `core/grist_importer.py` | POST /api/docs binary xlsx → docId |
| `core/archetype_engine.py` | Dispatch DashboardPlan → apply_actions() calls |
| `archetypes/hr.py` | HR template: builds apply action sequences from DashboardPlan |
| `archetypes/decisionnel.py` | DECISIONNEL template |
| `archetypes/support.py` | SUPPORT template |
| `archetypes/student.py` | STUDENT template |
| `archetypes/si.py` | SI template |
| `archetypes/project.py` | PROJECT template |
| `archetypes/generic.py` | GENERIC fallback template |
| `eval_classifier.py` | Prompt evaluation script (dev tool) |
| `prompts/` | 5 prompt variants per agent (20 files total) |

### Modified modules

| File | Change |
|---|---|
| `core/grist_api.py` | Add `apply_actions(doc_id, actions)` and `upload_excel(path)` |
| `main.py` | New CLI: `--input` replaces `--doc-name`/`--doc-id` |
| `config.py` | Add `MARKITDOWN_MAX_ROWS` setting |

### Removed modules

| File | Reason |
|---|---|
| `core/grist_analyzer.py` | Replaced by `data_analyzer.py` |
| `core/schema_analyzer.py` | Replaced by multi-agent pipeline |
| `core/grist_updater.py` | Replaced by `archetype_engine.py` |

---

## Structured Output — vLLM guided_json

Each LLM agent uses `extra_body` with `guided_json` derived from a Pydantic model:

```python
# Example: Domain Classifier
class ClassificationResult(BaseModel):
    archetype: Literal["HR","DECISIONNEL","SUPPORT","STUDENT","SI","PROJECT","GENERIC"]
    confidence: float
    table_mapping: dict[str, str]
    params: dict[str, str]

response = client.chat.completions.create(
    model=model_name,
    messages=messages,
    extra_body={"guided_json": ClassificationResult.model_json_schema()}
)
```

The `archetype` field additionally uses `guided_choice` for double constraint. All agents use this pattern.

---

## Prompt Evaluation Framework

```
prompts/
  data_analyzer_v1.md … data_analyzer_v5.md
  domain_classifier_v1.md … domain_classifier_v5.md
  insight_extractor_v1.md … insight_extractor_v5.md
  dashboard_composer_v1.md … dashboard_composer_v5.md

output/prompt_eval/
  {agent}_{version}.json    ← raw output + latency + token count
  report.md                 ← comparative table: archetype/insights/plan quality per version
```

Usage:
```bash
python eval_classifier.py --input samples/employees_rh.xlsx
python eval_classifier.py --input samples/sales_2024.xlsx --agent insight_extractor
```

Each run logs: detected archetype, confidence, insight count, plan page count, latency, token usage. `report.md` is regenerated after each run.

---

## Grist apply_actions — Validation Strategy

The exact Grist internal action format (`_grist_Views`, `_grist_ViewSections`, `_grist_TabBar`) must be validated against the live instance during implementation, following the same methodology as the REST endpoint validation (see `grist-api-documentation` skill). Each archetype template stores validated action sequences as Python functions, not freeform strings.

```python
# archetypes/hr.py
def _create_dashboard_page(api, doc_id, table_ref, sections):
    """Pre-tested action sequence for creating a page with chart sections."""
    actions = [
        ["AddRecord", "_grist_Views", None, {"name": "Dashboard RH"}],
        # ... validated action sequence
    ]
    return api.apply_actions(doc_id, actions)
```

---

## Error Handling

| Situation | Behavior |
|---|---|
| confidence < 0.6 | Force GENERIC archetype, log warning |
| Missing optional table in mapping | Template skips dependent sections, continues |
| apply_actions 400/500 | Log error per section, continue with remaining sections |
| markitdown fails | Raise with clear message: unsupported Excel format |
| vLLM guided_json validation fails | Retry once with stricter prompt, then raise |
| `--dry-run` | Print DashboardPlan JSON, skip upload and apply |

---

## Success Criteria

1. `python main.py --input employees_rh.xlsx` runs end-to-end without error
2. Grist document created with correct sheet-named tables
3. At least one page with chart sections created via `apply_actions`
4. Chart titles reflect actual insight findings from the data
5. Form page created for the primary table
6. `--dry-run` prints DashboardPlan without touching Grist
7. `eval_classifier.py` produces `report.md` comparing 5 prompt variants
8. All `table` and `col` values in LLM outputs match exact names from DataProfile
