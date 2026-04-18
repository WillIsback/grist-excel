# Grist apply_actions — Validated Format

Date: 2026-04-18
Grist server: http://localhost:8484
Test doc ID: new~qRyhQop9BSUjmwvRYUjwBY~5 (fresh upload of samples/employees_rh.xlsx)

---

## tableRef resolution

```
GET /api/docs/{docId}/tables/_grist_Tables/records
```

- Integer ref: top-level `"id"` field (e.g. `1`)
- String tableId: `fields.tableId` (e.g. `"Table1"`)

The REST endpoint `/api/docs/{docId}/tables` also returns `fields.tableRef` (same integer) for convenience.

---

## POST /api/docs/{docId}/apply — Request Body Format

**CRITICAL**: The body must be a **bare JSON array of action arrays**, NOT an object with an `"actions"` key.

```
CORRECT:   [["AddRecord", "TableName", null, {fields}], ...]
INCORRECT: {"actions": [["AddRecord", "TableName", null, {fields}], ...]}
```

The wrapped format returns: `{"error": "\`actions\` parameter should be an array."}`

**Bug in codebase**: `core/grist_api.py` method `apply_actions()` currently uses the wrong format (`json={"actions": actions}`). This must be fixed to `json=actions`.

---

## Internal table names (from SQLite schema)

| Plan assumed name       | Actual name              | Status   |
|-------------------------|--------------------------|----------|
| `_grist_ViewSections`   | `_grist_Views_section`   | WRONG    |
| `_grist_TabBar`         | `_grist_TabBar`          | Correct  |
| `_grist_Views`          | `_grist_Views`           | Correct  |
| `_grist_Pages`          | `_grist_Pages`           | Correct  |

Note: `_grist_ViewSections` does NOT exist. The REST API returns `{"error": "Table not found \"_grist_ViewSections\""}`. The correct table name is `_grist_Views_section`.

---

## Create page

```json
["AddRecord", "_grist_Views", null, {"name": "Page Name", "type": "raw_data"}]
```

- `name`: required — the page title shown in Grist UI
- `type`: optional — use `"raw_data"` to match UI-created pages; empty string also accepted
- Response: `{"actionNum": N, "retValues": [<viewId>], "isModification": true}`

### Full test result

```
POST body: [["AddRecord","_grist_Views",null,{"name":"Test Page","type":"raw_data"}]]
Response:  {"actionNum": 3, "retValues": [2], "isModification": true}
```

---

## Create TabBar entry

```json
["AddRecord", "_grist_TabBar", null, {"viewRef": <viewId>, "tabPos": <float>}]
```

- `viewRef`: required — integer ID of the view (from retValues of AddRecord to _grist_Views)
- `tabPos`: required — float/int position; use the viewId or a sequential number
- **Required: YES** — without a `_grist_TabBar` entry, the page does NOT appear in the Grist tab bar

### Full test result

```
POST body: [["AddRecord","_grist_TabBar",null,{"viewRef":2,"tabPos":2}]]
Response:  {"actionNum": 4, "retValues": [2], "isModification": true}
```

---

## Create _grist_Pages entry

```json
["AddRecord", "_grist_Pages", null, {"viewRef": <viewId>, "indentation": 0, "pagePos": <float>}]
```

- `viewRef`: required — integer ID of the view
- `indentation`: optional (default 0) — nesting depth in left panel
- `pagePos`: required — float/int position in the left panel page list
- **Required: YES** — without a `_grist_Pages` entry, the page does NOT appear in the left panel

### Fields in _grist_Pages (all observed)

```
viewRef, indentation, pagePos, shareRef, options
```

---

## Table section (record)

```json
["AddRecord", "_grist_Views_section", null, {
  "tableRef": <tableRef>,
  "parentId": <viewId>,
  "parentKey": "record"
}]
```

**Minimal required fields**: `tableRef`, `parentId`, `parentKey`

**Full recommended fields** (matching UI-created sections):

```json
["AddRecord", "_grist_Views_section", null, {
  "tableRef": 1,
  "parentId": 2,
  "parentKey": "record",
  "title": "",
  "defaultWidth": 100,
  "borderWidth": 1,
  "chartType": "",
  "sortColRefs": "[]",
  "linkSrcSectionRef": 0,
  "linkSrcColRef": 0,
  "linkTargetColRef": 0
}]
```

Response: `{"retValues": [<sectionId>]}`

---

## Chart section (bar chart)

```json
["AddRecord", "_grist_Views_section", null, {
  "tableRef": <tableRef>,
  "parentId": <viewId>,
  "parentKey": "chart",
  "chartType": "bar",
  "title": "",
  "defaultWidth": 100,
  "borderWidth": 1,
  "sortColRefs": "[]",
  "linkSrcSectionRef": 0,
  "linkSrcColRef": 0,
  "linkTargetColRef": 0
}]
```

- `parentKey`: `"chart"` — this is what determines the section type, NOT a separate `"type"` field
- `chartType`: `"bar"` — the chart variant; other valid values include `"line"`, `"pie"`, `"area"`

### Full test result

```
POST body includes "parentKey":"chart","chartType":"bar"
Response:  {"actionNum": 7, "retValues": [5], "isModification": true}
Verified:  _grist_Views_section id=5 has parentKey="chart", chartType="bar"
```

---

## Card list section (detail)

```json
["AddRecord", "_grist_Views_section", null, {
  "tableRef": <tableRef>,
  "parentId": <viewId>,
  "parentKey": "detail",
  "title": "",
  "defaultWidth": 100,
  "borderWidth": 1,
  "chartType": "",
  "sortColRefs": "[]",
  "linkSrcSectionRef": 0,
  "linkSrcColRef": 0,
  "linkTargetColRef": 0
}]
```

- `parentKey`: `"detail"` — card list in Grist is the "detail" section type

### Full test result

```
POST body includes "parentKey":"detail"
Response:  {"actionNum": 8, "retValues": [6], "isModification": true}
Verified:  _grist_Views_section id=6 has parentKey="detail"
```

---

## Form section

```json
["AddRecord", "_grist_Views_section", null, {
  "tableRef": <tableRef>,
  "parentId": <viewId>,
  "parentKey": "form",
  "title": "",
  "defaultWidth": 100,
  "borderWidth": 1,
  "chartType": "",
  "sortColRefs": "[]",
  "linkSrcSectionRef": 0,
  "linkSrcColRef": 0,
  "linkTargetColRef": 0
}]
```

- `parentKey`: `"form"` — form sections use "form"

### Full test result

```
POST body includes "parentKey":"form"
Response:  {"actionNum": 9, "retValues": [7], "isModification": true}
Verified:  _grist_Views_section id=7 has parentKey="form"
```

---

## Complete sequence to create a page with sections

```python
# Step 1: Create the view (page)
resp = api.apply_actions(doc_id, [
    ["AddRecord", "_grist_Views", None, {"name": "My Dashboard", "type": "raw_data"}]
])
view_id = resp["retValues"][0]

# Step 2: Register it in TabBar and Pages (both required for UI visibility)
api.apply_actions(doc_id, [
    ["AddRecord", "_grist_TabBar", None, {"viewRef": view_id, "tabPos": view_id}],
    ["AddRecord", "_grist_Pages",  None, {"viewRef": view_id, "indentation": 0, "pagePos": view_id}],
])

# Step 3: Add sections (can batch multiple section types in one call)
api.apply_actions(doc_id, [
    ["AddRecord", "_grist_Views_section", None, {
        "tableRef": table_ref, "parentId": view_id, "parentKey": "record",
        "title": "", "defaultWidth": 100, "borderWidth": 1,
        "chartType": "", "sortColRefs": "[]",
        "linkSrcSectionRef": 0, "linkSrcColRef": 0, "linkTargetColRef": 0
    }],
    ["AddRecord", "_grist_Views_section", None, {
        "tableRef": table_ref, "parentId": view_id, "parentKey": "chart",
        "chartType": "bar", "title": "", "defaultWidth": 100, "borderWidth": 1,
        "sortColRefs": "[]",
        "linkSrcSectionRef": 0, "linkSrcColRef": 0, "linkTargetColRef": 0
    }],
])
```

Note: Template back-references (e.g. `{{retValues[0]}}`) in field values do NOT work — they are stored as literal strings. Multi-step creation requires sequential API calls.

---

## All fields in _grist_Views_section

Observed on both UI-created and API-created sections:

```
tableRef, parentId, parentKey, title, description, defaultWidth, borderWidth,
theme, options, chartType, layoutSpec, filterSpec, sortColRefs,
linkSrcSectionRef, linkSrcColRef, linkTargetColRef, embedId, rules, shareOptions
```

**There is NO `type` field** in `_grist_Views_section`. The section type is determined entirely by `parentKey`.

---

## Deviations from plan defaults (docs/superpowers/plans/2026-04-18-plan-c-archetype-engine.md)

| Item | Plan assumed | Actual (validated) | Impact |
|------|-------------|-------------------|--------|
| Table name for sections | `_grist_ViewSections` | `_grist_Views_section` | CRITICAL — wrong name returns 404 |
| API body format | `{"actions": [...]}` | `[...]` (bare array) | CRITICAL — wrong format returns 400 |
| Section field for type | `"type": "record"` | No `type` field; use `"parentKey": "record"` | CRITICAL — wrong field |
| `parentKey` for table | `"primary"` | `"record"` | CRITICAL — wrong value |
| `parentKey` for card list | `"primary"` | `"detail"` | CRITICAL — wrong value |
| `_grist_Pages` entry | Not mentioned in plan steps | Required for page to appear in left panel | Important |
| `apply_actions()` in grist_api.py | Uses `json={"actions": actions}` | Must be `json=actions` | BUG in existing code |
| Template back-refs (`{{retValues[0]}}`) | Not attempted | Do not work — stored as literal string | Multi-step calls required |

---

## Summary: parentKey values by section type

| Grist UI widget | `parentKey` value |
|----------------|------------------|
| Table (grid)   | `"record"`        |
| Chart          | `"chart"`         |
| Card list      | `"detail"`        |
| Card (single)  | `"single"`        |
| Form           | `"form"`          |

The `"single"` value was observed in the auto-created `recordCardViewSectionRef` section
(id=3, parentId=0) — it is the card/record card type, separate from card list.
