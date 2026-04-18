# Design: grist-excel — Grist Document Analyzer

> **Status:** Current architecture as of 2026-04-18.
> Previous version described an Excel→Grist import tool (now removed).
> See `.plan/mvp-plan.md` history section for the pivot rationale.

---

## Concept

The user imports Excel into Grist natively (one click). This tool then analyzes the existing Grist document, uses a local LLM to suggest improvements (formulas, column type changes, widget recommendations), and applies them via the Grist REST API.

```
User imports Excel → Grist (manual, native feature)
                          ↓
        Tool: python main.py --doc-id {docId} --request "..."
                          ↓
              GristAPI: fetch tables + columns + records
                          ↓
              SchemaAnalyzer: build LLM prompt with stats
                          ↓
              LLM (vLLM): generate config JSON
                          ↓
              GristUpdater: apply formulas + column changes
                          ↓
              Text report: widget/dashboard recommendations
```

**Key constraint:** The Grist REST API allows reading/modifying tables, columns, and records. Widget/view creation requires `POST /api/docs/{docId}/apply` with Grist's internal undocumented action format. Therefore:
- Formulas → **applied automatically** via POST columns
- Column type changes → **applied automatically** via PATCH columns
- Widget recommendations → **text report only** (user applies manually)

---

## Architecture

### Modules

```
grist-excel/
├── core/
│   ├── grist_api.py          # Grist REST API client
│   ├── grist_analyzer.py     # Fetch document structure + data
│   ├── schema_analyzer.py    # Build LLM prompt from document info
│   ├── grist_updater.py      # Apply LLM config via API
│   └── model_discovery.py    # Select vLLM model dynamically
├── main.py                   # CLI orchestrator
├── config.py                 # Settings (pydantic-settings)
└── tests/
    ├── test_grist_analyzer.py
    ├── test_schema_analyzer.py
    ├── test_grist_updater.py
    └── test_main.py
```

### Data Flow

```
GristAnalyzer.analyze(doc_id)
  → GristAPI.get_tables(doc_id)               # GET /api/docs/{docId}/tables
  → GristAPI.get_columns(doc_id, table_id)    # GET /api/docs/{docId}/tables/{tid}/columns
  → GristAPI.get_records(doc_id, table_id)    # GET /api/docs/{docId}/tables/{tid}/records
  → _compute_stats(records, columns)
  → GristDocumentInfo

SchemaAnalyzer(document_info, user_request)
  → build_messages()  →  [system_prompt, user_prompt]

call_llm(messages) → config JSON

GristUpdater.apply_config(doc_id, config)
  → _apply_formula()      → GristAPI.add_columns()    # POST /columns
  → _apply_column_change() → GristAPI.patch_columns() # PATCH /columns
```

---

## API Endpoints Used

| Operation | Method | Endpoint |
|---|---|---|
| List orgs | GET | `/api/orgs` |
| List workspaces | GET | `/api/orgs/{orgId}/workspaces` |
| Create document | POST | `/api/workspaces/{wsId}/docs` |
| List tables | GET | `/api/docs/{docId}/tables` |
| Create table | POST | `/api/docs/{docId}/tables` |
| List columns | GET | `/api/docs/{docId}/tables/{tid}/columns` |
| Add columns | POST | `/api/docs/{docId}/tables/{tid}/columns` |
| Modify columns | PATCH | `/api/docs/{docId}/tables/{tid}/columns` |
| Get records | GET | `/api/docs/{docId}/tables/{tid}/records` |
| Add records | POST | `/api/docs/{docId}/tables/{tid}/records` |
| Update records | PATCH | `/api/docs/{docId}/tables/{tid}/records` |

**Important:** `GET /tables` does NOT return column definitions. Columns require a separate `GET /tables/{tid}/columns` call.

---

## LLM Config JSON Format

```json
{
  "formulas": [
    {
      "table": "Ventes",
      "column": "TotalTTC",
      "type": "Numeric",
      "formula": "@Montant * 1.20",
      "label": "Total TTC"
    }
  ],
  "columnChanges": [
    {
      "table": "Ventes",
      "column": "Statut",
      "newType": "Choice",
      "choices": ["Livré", "En cours", "Annulé"]
    }
  ],
  "recommendations": [
    {
      "widget": "Chart",
      "description": "Graphique des ventes par mois",
      "table": "Ventes",
      "x": "Mois",
      "y": "TotalTTC",
      "aggregation": "sum"
    }
  ]
}
```

---

## Type Normalization

All type normalization goes through `GristAPI.normalize_grist_type()`. The canonical mapping:

| LLM alias | Grist API type |
|---|---|
| `Int` | `Integer` |
| `Float` | `Numeric` |
| `Bool` | `Toggle` |
| `Ref` | `Reference` |
| `Integer`, `Numeric`, `Text`, `Date`, `DateTime`, `Toggle`, `Choice` | pass-through |

---

## URL Construction

All URLs are built via `GristAPI._api_url(path)` which prepends `server` and optional `api_prefix`. `_doc_url()` and `_ws_url()` both delegate to `_api_url()`.

---

## Error Handling

```
GristConnectionError   — server unreachable or timeout
GristAuthError         — 401/403
GristAPIError(status, message) — 4xx/5xx from API
```

`_request_with_retry()` retries 3× with exponential backoff on `ConnectionError`, `Timeout`, and HTTP 5xx. Always raises after exhausting retries.

---

## CLI

```bash
python main.py --doc-id {docId} --request "Dashboard de ventes"
python main.py --doc-id {docId} --request "Améliorer le document" --dry-run
python main.py --doc-id {docId} --request "Formules TVA" --model qwen3-8b
```

`--dry-run` prints the LLM config without applying it to Grist.
