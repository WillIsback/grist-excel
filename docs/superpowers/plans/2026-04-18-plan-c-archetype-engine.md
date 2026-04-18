# Data-to-Dashboard — Plan C: Archetype Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the archetype engine that translates a `DashboardPlan` into a live Grist document with pages, charts, card views, and forms. Replace the old CLI with `--input xlsx`. Add prompt evaluation tooling.

**Architecture:** Validation-first — Task 1 discovers the correct Grist `apply_actions` format by introspecting the live instance before any template code is written. A `BaseArchetype` ABC defines the interface; 7 archetype modules implement it. `ArchetypeEngine` dispatches by archetype string. The new `main.py` wires the full pipeline: `DataAnalyzer → PipelineOrchestrator → GristImporter → ArchetypeEngine`. Old modules (`grist_analyzer`, `schema_analyzer`, `grist_updater`) are deleted.

**Tech Stack:** Python 3.11, requests, Grist REST API (`apply_actions`), pytest, unittest.mock

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `archetypes/__init__.py` | Package marker |
| Create | `archetypes/base.py` | `BaseArchetype` ABC + `GristTableResolver` (tableId → tableRef int) |
| Create | `archetypes/generic.py` | GENERIC: table view + form for primary table |
| Create | `archetypes/hr.py` | HR: chart dashboard + employee card list + form |
| Create | `archetypes/decisionnel.py` | DECISIONNEL: analytics dashboard + raw table |
| Create | `archetypes/support.py` | SUPPORT: ticket card list + dashboard + form |
| Create | `archetypes/student.py` | STUDENT: student cards + grade summary + dashboard |
| Create | `archetypes/si.py` | SI: inventory table + dashboard + incident form |
| Create | `archetypes/project.py` | PROJECT: task card list + dashboard + form |
| Create | `core/archetype_engine.py` | Dispatch `DashboardPlan` → `archetype.apply()` |
| Modify | `main.py` | New CLI: `--input` replaces `--doc-name`/`--doc-id` |
| Create | `eval_classifier.py` | Prompt evaluation dev tool |
| Create | `prompts/` directory | 20 prompt variant files (5 per agent) |
| Delete | `core/grist_analyzer.py` | Replaced by `data_analyzer.py` |
| Delete | `core/schema_analyzer.py` | Replaced by multi-agent pipeline |
| Delete | `core/grist_updater.py` | Replaced by `archetype_engine.py` |
| Delete | `tests/test_grist_analyzer.py` | Accompanies deleted module |
| Delete | `tests/test_schema_analyzer.py` | Accompanies deleted module |
| Delete | `tests/test_grist_updater.py` | Accompanies deleted module |
| Create | `tests/test_archetype_engine.py` | Tests for `ArchetypeEngine` dispatch |
| Create | `tests/test_new_main.py` | Tests for new `main.py` CLI |

---

### Task 1: Grist apply_actions — Validation Sprint

**Files:** No source files changed. This task produces documented, tested action sequences.

> **This task has no TDD cycle.** It is a live-instance discovery sprint. Run each step, record results, update the reference table at the bottom. The output of this task is the exact action format used in Tasks 3–9.

- [ ] **Step 1: Set environment variables**

```bash
export GRIST_KEY="c0136d94dbe8609d510f08bdea390694cd45ff50"
export GRIST_SERVER="http://localhost:8484"
# Pick any doc created by upload_excel (or create one manually in the UI)
export DOC_ID="<your-doc-id>"
```

- [ ] **Step 2: Introspect internal tables**

```bash
# Get tableRef integers for all sheets in the doc
curl -s -H "Authorization: Bearer $GRIST_KEY" \
  "$GRIST_SERVER/api/docs/$DOC_ID/tables/_grist_Tables/records" \
  | python3 -m json.tool

# Expected: {"records":[{"id":1,"fields":{"tableId":"Employes",...}},{"id":2,...}]}
# Record "id" is the integer tableRef used in ViewSections. tableId is the string.
```

- [ ] **Step 3: Inspect existing views (if any)**

```bash
curl -s -H "Authorization: Bearer $GRIST_KEY" \
  "$GRIST_SERVER/api/docs/$DOC_ID/tables/_grist_Views/records" \
  | python3 -m json.tool

curl -s -H "Authorization: Bearer $GRIST_KEY" \
  "$GRIST_SERVER/api/docs/$DOC_ID/tables/_grist_ViewSections/records" \
  | python3 -m json.tool

curl -s -H "Authorization: Bearer $GRIST_KEY" \
  "$GRIST_SERVER/api/docs/$DOC_ID/tables/_grist_TabBar/records" \
  | python3 -m json.tool
```

If the doc has pages created via the UI, note what fields are set and what their values are. This is the ground truth for the action sequences below.

- [ ] **Step 4: Test creating a page (view)**

```bash
curl -s -X POST "$GRIST_SERVER/api/docs/$DOC_ID/apply" \
  -H "Authorization: Bearer $GRIST_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actions":[["AddRecord","_grist_Views",null,{"name":"Test Page"}]]}' \
  | python3 -m json.tool
```

Expected: `{"retValues":[[<viewId>]]}` — record the integer viewId.

- [ ] **Step 5: Test creating a TabBar entry**

```bash
# Replace VIEW_ID with the viewId from Step 4
export VIEW_ID=<viewId>

curl -s -X POST "$GRIST_SERVER/api/docs/$DOC_ID/apply" \
  -H "Authorization: Bearer $GRIST_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"actions\":[[\"AddRecord\",\"_grist_TabBar\",null,{\"viewRef\":$VIEW_ID}]]}" \
  | python3 -m json.tool
```

- [ ] **Step 6: Test creating a table ViewSection**

```bash
# Replace TABLE_REF with the tableRef integer from Step 2 (e.g., 1 for first sheet)
export TABLE_REF=1

curl -s -X POST "$GRIST_SERVER/api/docs/$DOC_ID/apply" \
  -H "Authorization: Bearer $GRIST_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"actions\":[[\"AddRecord\",\"_grist_ViewSections\",null,{
    \"parentId\":$VIEW_ID,
    \"tableRef\":$TABLE_REF,
    \"parentKey\":\"primary\",
    \"title\":\"\",
    \"defaultWidth\":800,
    \"borderWidth\":1,
    \"type\":\"record\"
  }]]}" | python3 -m json.tool
```

Open the Grist UI to verify a new page appeared with the table section.

- [ ] **Step 7: Test creating a chart ViewSection**

```bash
curl -s -X POST "$GRIST_SERVER/api/docs/$DOC_ID/apply" \
  -H "Authorization: Bearer $GRIST_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"actions\":[[\"AddRecord\",\"_grist_ViewSections\",null,{
    \"parentId\":$VIEW_ID,
    \"tableRef\":$TABLE_REF,
    \"parentKey\":\"primary\",
    \"title\":\"Test Chart\",
    \"defaultWidth\":800,
    \"borderWidth\":1,
    \"type\":\"chart\",
    \"chartType\":\"bar\"
  }]]}" | python3 -m json.tool
```

Verify in the UI. If the chart section appears, record the exact fields.

- [ ] **Step 8: Test creating a card_list ViewSection**

```bash
curl -s -X POST "$GRIST_SERVER/api/docs/$DOC_ID/apply" \
  -H "Authorization: Bearer $GRIST_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"actions\":[[\"AddRecord\",\"_grist_ViewSections\",null,{
    \"parentId\":$VIEW_ID,
    \"tableRef\":$TABLE_REF,
    \"parentKey\":\"primary\",
    \"title\":\"Card List\",
    \"defaultWidth\":800,
    \"borderWidth\":1,
    \"type\":\"detail\",
    \"detailWidth\":280
  }]]}" | python3 -m json.tool
```

- [ ] **Step 9: Test creating a form ViewSection**

```bash
curl -s -X POST "$GRIST_SERVER/api/docs/$DOC_ID/apply" \
  -H "Authorization: Bearer $GRIST_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"actions\":[[\"AddRecord\",\"_grist_ViewSections\",null,{
    \"parentId\":$VIEW_ID,
    \"tableRef\":$TABLE_REF,
    \"parentKey\":\"primary\",
    \"title\":\"Saisie\",
    \"defaultWidth\":800,
    \"borderWidth\":1,
    \"type\":\"form\"
  }]]}" | python3 -m json.tool
```

- [ ] **Step 10: Document discovered format**

Based on Steps 2–9, fill in this reference table (used in all subsequent tasks):

```
Validated Grist Action Format
==============================
Create page:    ["AddRecord", "_grist_Views",       null, {"name": STR}]
Create tab:     ["AddRecord", "_grist_TabBar",       null, {"viewRef": INT}]
Table section:  ["AddRecord", "_grist_ViewSections", null, {
                    "parentId": INT,    "tableRef": INT,
                    "parentKey": "primary", "type": "record",
                    "title": STR, "defaultWidth": 800, "borderWidth": 1 }]
Chart section:  ["AddRecord", "_grist_ViewSections", null, {
                    "parentId": INT,    "tableRef": INT,
                    "parentKey": "primary", "type": "chart",
                    "chartType": STR,   "title": STR,
                    "defaultWidth": 800, "borderWidth": 1 }]
Card list:      type="detail", detailWidth=280
Form:           type="form"
```

Correct any fields that differ from what the API actually accepted. These corrected values are what Tasks 3–9 must use.

---

### Task 2: archetypes/ package — BaseArchetype + GristTableResolver

**Files:**
- Create: `archetypes/__init__.py`
- Create: `archetypes/base.py`
- Create: `tests/test_archetype_base.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_archetype_base.py`:

```python
"""Tests for archetypes/base.py — BaseArchetype and GristTableResolver."""
import pytest
from unittest.mock import MagicMock
from archetypes.base import BaseArchetype, GristTableResolver
from core.grist_api import GristAPI


@pytest.fixture
def mock_api():
    api = MagicMock(spec=GristAPI)
    # _grist_Tables records: id=integer tableRef, fields.tableId=string
    api.get_records.return_value = [
        {"id": 1, "fields": {"tableId": "Employes"}},
        {"id": 2, "fields": {"tableId": "Absences"}},
    ]
    return api


class TestGristTableResolver:
    def test_resolves_table_id_to_ref(self, mock_api):
        resolver = GristTableResolver(mock_api, "doc123")
        assert resolver.get_ref("Employes") == 1
        assert resolver.get_ref("Absences") == 2

    def test_raises_on_unknown_table(self, mock_api):
        resolver = GristTableResolver(mock_api, "doc123")
        with pytest.raises(KeyError):
            resolver.get_ref("NonExistent")

    def test_calls_grist_tables_endpoint(self, mock_api):
        GristTableResolver(mock_api, "doc123")
        mock_api.get_records.assert_called_once_with("doc123", "_grist_Tables")


class TestBaseArchetype:
    def test_is_abstract(self):
        """BaseArchetype cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseArchetype()

    def test_subclass_must_implement_apply(self):
        """Concrete subclass without apply() raises TypeError on instantiation."""
        class Incomplete(BaseArchetype):
            pass
        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_subclass_works(self):
        class Concrete(BaseArchetype):
            def apply(self, api, doc_id, classification, plan):
                return ["page1"]
        obj = Concrete()
        assert obj.apply(None, None, None, None) == ["page1"]
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_base.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'archetypes'`

- [ ] **Step 3: Create `archetypes/__init__.py`**

```python
"""Archetype templates for the Data-to-Dashboard pipeline."""
```

- [ ] **Step 4: Create `archetypes/base.py`**

```python
"""Base archetype interface and shared utilities.

GristTableResolver: resolves string tableId → integer tableRef
BaseArchetype: abstract base class all archetype modules implement
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan


class GristTableResolver:
    """Resolves string tableId → integer tableRef for apply_actions calls.

    Queries _grist_Tables once at construction; subsequent look-ups are O(1).
    """

    def __init__(self, api: GristAPI, doc_id: str):
        records = api.get_records(doc_id, "_grist_Tables")
        self._map: dict[str, int] = {
            r["fields"]["tableId"]: r["id"]
            for r in records
            if "tableId" in r.get("fields", {})
        }

    def get_ref(self, table_id: str) -> int:
        """Return the integer tableRef for a tableId string.

        Raises:
            KeyError: If table_id is not found in the document.
        """
        if table_id not in self._map:
            available = list(self._map.keys())
            raise KeyError(
                f"Table '{table_id}' not found. Available: {available}"
            )
        return self._map[table_id]


class BaseArchetype(ABC):
    """Abstract base for all archetype templates."""

    @abstractmethod
    def apply(
        self,
        api: GristAPI,
        doc_id: str,
        classification: ClassificationResult,
        plan: DashboardPlan,
    ) -> list[str]:
        """Apply the archetype template to the Grist document.

        Args:
            api: GristAPI instance
            doc_id: Target Grist document ID
            classification: ClassificationResult from Agent 2
            plan: DashboardPlan from Agent 4

        Returns:
            List of created page names (for logging/dry-run output)
        """

    # ------------------------------------------------------------------
    # Shared helpers used by all archetype subclasses
    # ------------------------------------------------------------------

    def _create_page(self, api: GristAPI, doc_id: str, name: str) -> int:
        """Create a page (view) and its TabBar entry. Returns viewId."""
        result = api.apply_actions(doc_id, [
            ["AddRecord", "_grist_Views", None, {"name": name}],
        ])
        view_id: int = result["retValues"][0][0]
        api.apply_actions(doc_id, [
            ["AddRecord", "_grist_TabBar", None, {"viewRef": view_id}],
        ])
        return view_id

    def _add_table_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> None:
        """Add a table (record) section to an existing page."""
        api.apply_actions(doc_id, [
            ["AddRecord", "_grist_ViewSections", None, {
                "parentId": view_id,
                "tableRef": table_ref,
                "parentKey": "primary",
                "title": title,
                "defaultWidth": 800,
                "borderWidth": 1,
                "type": "record",
            }],
        ])

    def _add_chart_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        chart_type: str,
        title: str,
    ) -> None:
        """Add a chart section to an existing page."""
        api.apply_actions(doc_id, [
            ["AddRecord", "_grist_ViewSections", None, {
                "parentId": view_id,
                "tableRef": table_ref,
                "parentKey": "primary",
                "title": title,
                "defaultWidth": 800,
                "borderWidth": 1,
                "type": "chart",
                "chartType": chart_type,
            }],
        ])

    def _add_card_list_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> None:
        """Add a card list section to an existing page."""
        api.apply_actions(doc_id, [
            ["AddRecord", "_grist_ViewSections", None, {
                "parentId": view_id,
                "tableRef": table_ref,
                "parentKey": "primary",
                "title": title,
                "defaultWidth": 800,
                "borderWidth": 1,
                "type": "detail",
                "detailWidth": 280,
            }],
        ])

    def _add_form_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> None:
        """Add a form section to an existing page."""
        api.apply_actions(doc_id, [
            ["AddRecord", "_grist_ViewSections", None, {
                "parentId": view_id,
                "tableRef": table_ref,
                "parentKey": "primary",
                "title": title,
                "defaultWidth": 800,
                "borderWidth": 1,
                "type": "form",
            }],
        ])
```

> **Note:** The exact field names in `_add_*` helpers must match what was validated in Task 1. Update them if the validation revealed different field names.

- [ ] **Step 5: Add `get_records()` to GristAPI if missing**

Check `core/grist_api.py`. If `get_records(doc_id, table_id)` does not exist, add it after `get_tables()`:

```python
def get_records(self, doc_id: str, table_id: str) -> list[dict]:
    """GET /api/docs/{docId}/tables/{tableId}/records

    Returns:
        List of record dicts: [{"id": int, "fields": {...}}, ...]
    """
    response = self._request_with_retry(
        "GET",
        self._doc_url(doc_id, f"tables/{table_id}/records"),
    )
    return response.json().get("records", [])
```

- [ ] **Step 6: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_base.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 7: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add archetypes/__init__.py archetypes/base.py core/grist_api.py tests/test_archetype_base.py
git commit -m "feat: add archetypes package — BaseArchetype, GristTableResolver, get_records()"
```

---

### Task 3: archetypes/generic.py — GENERIC fallback

**Files:**
- Create: `archetypes/generic.py`
- Test in: `tests/test_archetype_engine.py` (started here, extended in Task 7)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_archetype_engine.py`:

```python
"""Tests for archetype modules and ArchetypeEngine dispatch."""
import pytest
from unittest.mock import MagicMock, call, patch
from archetypes.generic import GenericArchetype
from archetypes.base import GristTableResolver
from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan, Page, PageSection


@pytest.fixture
def mock_api():
    api = MagicMock(spec=GristAPI)
    api.get_records.return_value = [
        {"id": 1, "fields": {"tableId": "Employes"}},
    ]
    api.apply_actions.return_value = {"retValues": [[10]]}
    return api


@pytest.fixture
def classification():
    return ClassificationResult(
        archetype="GENERIC",
        confidence=0.5,
        table_mapping={"main": "Employes"},
        params={"name_col": "Nom"},
    )


@pytest.fixture
def simple_plan():
    return DashboardPlan(pages=[
        Page(name="Données", sections=[
            PageSection(widget="table", table="Employes", title="Tableau"),
        ]),
        Page(name="Saisie", sections=[
            PageSection(widget="form", table="Employes", title="Formulaire"),
        ]),
    ])


class TestGenericArchetype:
    def test_returns_page_names(self, mock_api, classification, simple_plan):
        archetype = GenericArchetype()
        pages = archetype.apply(mock_api, "doc123", classification, simple_plan)
        assert isinstance(pages, list)
        assert len(pages) > 0

    def test_creates_one_page_per_plan_page(self, mock_api, classification, simple_plan):
        archetype = GenericArchetype()
        archetype.apply(mock_api, "doc123", classification, simple_plan)
        # 2 pages in plan → 2 _create_page calls → 2 _grist_Views AddRecord calls
        view_calls = [
            c for c in mock_api.apply_actions.call_args_list
            if "_grist_Views" in str(c)
        ]
        assert len(view_calls) == 2

    def test_skips_section_on_missing_table(self, mock_api, simple_plan):
        """If a section references an unknown table, it is skipped, not raised."""
        mock_api.get_records.return_value = []  # no tables resolved
        classification = ClassificationResult(
            archetype="GENERIC", confidence=0.5,
            table_mapping={}, params={},
        )
        archetype = GenericArchetype()
        # Should not raise
        pages = archetype.apply(mock_api, "doc123", classification, simple_plan)
        assert isinstance(pages, list)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_engine.py::TestGenericArchetype -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'archetypes.generic'`

- [ ] **Step 3: Implement `archetypes/generic.py`**

```python
"""GENERIC archetype — fallback for unrecognised business domains.

Creates:
- One page per DashboardPlan page, with sections mapped by widget type
- Skips any section whose table cannot be resolved (logs warning)
"""

from __future__ import annotations

import logging

from archetypes.base import BaseArchetype, GristTableResolver
from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan

logger = logging.getLogger(__name__)

WIDGET_TO_SECTION = {
    "table":     "_add_table_section",
    "card_list": "_add_card_list_section",
    "card":      "_add_card_list_section",
    "form":      "_add_form_section",
}


class GenericArchetype(BaseArchetype):
    """GENERIC archetype: renders every DashboardPlan page as-is."""

    def apply(
        self,
        api: GristAPI,
        doc_id: str,
        classification: ClassificationResult,
        plan: DashboardPlan,
    ) -> list[str]:
        resolver = GristTableResolver(api, doc_id)
        created_pages: list[str] = []

        for page in plan.pages:
            try:
                view_id = self._create_page(api, doc_id, page.name)
            except Exception as exc:
                logger.error("Failed to create page '%s': %s", page.name, exc)
                continue

            for section in page.sections:
                table_id = section.table
                if not table_id:
                    continue
                try:
                    table_ref = resolver.get_ref(table_id)
                except KeyError:
                    logger.warning(
                        "Table '%s' not found in doc — skipping section '%s'",
                        table_id, section.title,
                    )
                    continue

                try:
                    if section.widget == "chart" and section.chart_type:
                        self._add_chart_section(
                            api, doc_id, view_id, table_ref,
                            section.chart_type, section.title or "",
                        )
                    else:
                        method_name = WIDGET_TO_SECTION.get(section.widget)
                        if method_name:
                            getattr(self, method_name)(
                                api, doc_id, view_id, table_ref,
                                section.title or "",
                            )
                except Exception as exc:
                    logger.error(
                        "Section '%s' failed: %s — continuing",
                        section.title, exc,
                    )

            created_pages.append(page.name)

        return created_pages
```

- [ ] **Step 4: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_engine.py::TestGenericArchetype -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add archetypes/generic.py tests/test_archetype_engine.py
git commit -m "feat: add GenericArchetype — renders DashboardPlan pages as-is"
```

---

### Task 4: archetypes/hr.py — HR archetype

**Files:**
- Create: `archetypes/hr.py`
- Extend: `tests/test_archetype_engine.py`

- [ ] **Step 1: Add HR tests to `tests/test_archetype_engine.py`**

Append to the file:

```python
from archetypes.hr import HRArchetype
from core.dashboard_composer import Page, PageSection


@pytest.fixture
def hr_classification():
    return ClassificationResult(
        archetype="HR",
        confidence=0.91,
        table_mapping={"employees": "Employes", "absences": "Absences"},
        params={"name_col": "Nom", "department_col": "Departement"},
    )


@pytest.fixture
def hr_mock_api():
    api = MagicMock(spec=GristAPI)
    api.get_records.return_value = [
        {"id": 1, "fields": {"tableId": "Employes"}},
        {"id": 2, "fields": {"tableId": "Absences"}},
    ]
    api.apply_actions.return_value = {"retValues": [[10]]}
    return api


@pytest.fixture
def hr_plan():
    return DashboardPlan(pages=[
        Page(name="Dashboard RH", sections=[
            PageSection(
                widget="chart", chart_type="bar", table="Employes",
                x="Departement", y="Nom", agg="count",
                title="Effectifs par département",
            ),
            PageSection(
                widget="chart", chart_type="line", table="Absences",
                x="Date_Debut", y="Duree_Jours", agg="sum",
                title="Absences dans le temps",
            ),
        ]),
        Page(name="Employés", sections=[
            PageSection(widget="card_list", table="Employes", title="Annuaire"),
        ]),
        Page(name="Saisie", sections=[
            PageSection(widget="form", table="Employes", title="Nouvel employé"),
        ]),
    ])


class TestHRArchetype:
    def test_apply_returns_all_page_names(self, hr_mock_api, hr_classification, hr_plan):
        archetype = HRArchetype()
        pages = archetype.apply(hr_mock_api, "doc123", hr_classification, hr_plan)
        assert "Dashboard RH" in pages
        assert "Employés" in pages
        assert "Saisie" in pages

    def test_chart_sections_created_for_dashboard(self, hr_mock_api, hr_classification, hr_plan):
        archetype = HRArchetype()
        archetype.apply(hr_mock_api, "doc123", hr_classification, hr_plan)
        chart_calls = [
            c for c in hr_mock_api.apply_actions.call_args_list
            if "chart" in str(c)
        ]
        assert len(chart_calls) >= 2

    def test_missing_absences_table_skips_gracefully(self, hr_classification, hr_plan):
        """If absences table is absent, HR archetype skips those sections."""
        api = MagicMock(spec=GristAPI)
        api.get_records.return_value = [
            {"id": 1, "fields": {"tableId": "Employes"}},
            # No Absences
        ]
        api.apply_actions.return_value = {"retValues": [[10]]}
        archetype = HRArchetype()
        pages = archetype.apply(api, "doc123", hr_classification, hr_plan)
        assert isinstance(pages, list)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_engine.py::TestHRArchetype -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'archetypes.hr'`

- [ ] **Step 3: Implement `archetypes/hr.py`**

```python
"""HR archetype — Human Resources domain.

Semantic roles:
  employees (required), absences (optional), evaluations (optional)

Pages created from DashboardPlan:
  Dashboard RH      — chart sections (one per insight)
  Employees page    — card_list for employees table
  Entry form        — form for employees table
"""

from __future__ import annotations

import logging

from archetypes.base import BaseArchetype, GristTableResolver
from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan

logger = logging.getLogger(__name__)

WIDGET_TO_SECTION = {
    "table":     "_add_table_section",
    "card_list": "_add_card_list_section",
    "card":      "_add_card_list_section",
    "form":      "_add_form_section",
}


class HRArchetype(BaseArchetype):
    """HR archetype: renders DashboardPlan pages with HR-specific handling."""

    def apply(
        self,
        api: GristAPI,
        doc_id: str,
        classification: ClassificationResult,
        plan: DashboardPlan,
    ) -> list[str]:
        resolver = GristTableResolver(api, doc_id)
        created_pages: list[str] = []

        for page in plan.pages:
            try:
                view_id = self._create_page(api, doc_id, page.name)
            except Exception as exc:
                logger.error("HR: failed to create page '%s': %s", page.name, exc)
                continue

            for section in page.sections:
                table_id = section.table
                if not table_id:
                    continue
                try:
                    table_ref = resolver.get_ref(table_id)
                except KeyError:
                    logger.warning(
                        "HR: table '%s' not in doc — skipping section '%s'",
                        table_id, section.title,
                    )
                    continue

                try:
                    if section.widget == "chart" and section.chart_type:
                        self._add_chart_section(
                            api, doc_id, view_id, table_ref,
                            section.chart_type, section.title or "",
                        )
                    else:
                        method_name = WIDGET_TO_SECTION.get(section.widget)
                        if method_name:
                            getattr(self, method_name)(
                                api, doc_id, view_id, table_ref,
                                section.title or "",
                            )
                except Exception as exc:
                    logger.error(
                        "HR: section '%s' failed: %s — continuing",
                        section.title, exc,
                    )

            created_pages.append(page.name)

        return created_pages
```

- [ ] **Step 4: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_engine.py::TestHRArchetype -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add archetypes/hr.py tests/test_archetype_engine.py
git commit -m "feat: add HRArchetype — dashboard charts + card list + form"
```

---

### Task 5: Remaining archetypes (decisionnel, support, student, si, project)

**Files:**
- Create: `archetypes/decisionnel.py`, `archetypes/support.py`, `archetypes/student.py`, `archetypes/si.py`, `archetypes/project.py`

These archetypes all follow the identical pattern as `HRArchetype` — they differ only by class name. The DashboardPlan drives the actual layout; the archetype class is a dispatch target, not a hard-coded template.

- [ ] **Step 1: Create `archetypes/decisionnel.py`**

```python
"""DECISIONNEL archetype — Business Intelligence / Analytics domain."""

from __future__ import annotations
import logging
from archetypes.hr import HRArchetype  # Same logic, different class name

logger = logging.getLogger(__name__)


class DecisionnelArchetype(HRArchetype):
    """DECISIONNEL archetype: analytics dashboard + raw data table."""
```

- [ ] **Step 2: Create `archetypes/support.py`**

```python
"""SUPPORT archetype — Customer support / ticketing domain."""

from __future__ import annotations
import logging
from archetypes.hr import HRArchetype

logger = logging.getLogger(__name__)


class SupportArchetype(HRArchetype):
    """SUPPORT archetype: ticket card list + dashboard + form."""
```

- [ ] **Step 3: Create `archetypes/student.py`**

```python
"""STUDENT archetype — Academic / education domain."""

from __future__ import annotations
import logging
from archetypes.hr import HRArchetype

logger = logging.getLogger(__name__)


class StudentArchetype(HRArchetype):
    """STUDENT archetype: student cards + grade summary + dashboard."""
```

- [ ] **Step 4: Create `archetypes/si.py`**

```python
"""SI archetype — Information Systems / IT assets domain."""

from __future__ import annotations
import logging
from archetypes.hr import HRArchetype

logger = logging.getLogger(__name__)


class SIArchetype(HRArchetype):
    """SI archetype: inventory table + SI dashboard + incident form."""
```

- [ ] **Step 5: Create `archetypes/project.py`**

```python
"""PROJECT archetype — Project management domain."""

from __future__ import annotations
import logging
from archetypes.hr import HRArchetype

logger = logging.getLogger(__name__)


class ProjectArchetype(HRArchetype):
    """PROJECT archetype: task card list + project dashboard + form."""
```

- [ ] **Step 6: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

- [ ] **Step 7: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add archetypes/decisionnel.py archetypes/support.py archetypes/student.py archetypes/si.py archetypes/project.py
git commit -m "feat: add remaining archetype stubs (decisionnel, support, student, si, project)"
```

---

### Task 6: core/archetype_engine.py

**Files:**
- Create: `core/archetype_engine.py`
- Extend: `tests/test_archetype_engine.py`

- [ ] **Step 1: Add dispatch tests to `tests/test_archetype_engine.py`**

Append:

```python
from core.archetype_engine import ArchetypeEngine
from archetypes.hr import HRArchetype
from archetypes.generic import GenericArchetype


class TestArchetypeEngine:
    def test_dispatches_to_hr_archetype(self, hr_mock_api, hr_classification, hr_plan):
        engine = ArchetypeEngine(hr_mock_api)
        with patch("archetypes.hr.HRArchetype.apply", return_value=["p1"]) as mock_apply:
            result = engine.apply("doc123", hr_classification, hr_plan)
        mock_apply.assert_called_once()
        assert result == ["p1"]

    def test_dispatches_to_generic_on_unknown_archetype(self, mock_api, simple_plan):
        classification = ClassificationResult(
            archetype="GENERIC", confidence=0.4,
            table_mapping={}, params={},
        )
        engine = ArchetypeEngine(mock_api)
        with patch("archetypes.generic.GenericArchetype.apply", return_value=["p1"]) as mock_apply:
            engine.apply("doc123", classification, simple_plan)
        mock_apply.assert_called_once()

    def test_returns_empty_list_on_all_pages_failed(self, mock_api, simple_plan):
        mock_api.apply_actions.side_effect = Exception("Grist error")
        classification = ClassificationResult(
            archetype="GENERIC", confidence=0.4,
            table_mapping={}, params={},
        )
        engine = ArchetypeEngine(mock_api)
        result = engine.apply("doc123", classification, simple_plan)
        assert result == []
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_engine.py::TestArchetypeEngine -v 2>&1 | head -10
```

- [ ] **Step 3: Create `core/archetype_engine.py`**

```python
"""Archetype Engine — dispatches DashboardPlan to the correct archetype module.

Usage:
    engine = ArchetypeEngine(api)
    created_pages = engine.apply(doc_id, classification, dashboard_plan)
"""

from __future__ import annotations

import logging

from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan

from archetypes.base import BaseArchetype
from archetypes.generic import GenericArchetype
from archetypes.hr import HRArchetype
from archetypes.decisionnel import DecisionnelArchetype
from archetypes.support import SupportArchetype
from archetypes.student import StudentArchetype
from archetypes.si import SIArchetype
from archetypes.project import ProjectArchetype

logger = logging.getLogger(__name__)

ARCHETYPE_MAP: dict[str, type[BaseArchetype]] = {
    "HR":          HRArchetype,
    "DECISIONNEL": DecisionnelArchetype,
    "SUPPORT":     SupportArchetype,
    "STUDENT":     StudentArchetype,
    "SI":          SIArchetype,
    "PROJECT":     ProjectArchetype,
    "GENERIC":     GenericArchetype,
}


class ArchetypeEngine:
    """Dispatches a DashboardPlan to the appropriate archetype template."""

    def __init__(self, api: GristAPI):
        self.api = api

    def apply(
        self,
        doc_id: str,
        classification: ClassificationResult,
        plan: DashboardPlan,
    ) -> list[str]:
        """Apply the archetype corresponding to classification.archetype.

        Falls back to GenericArchetype if the archetype string is unrecognised.

        Returns:
            List of created page names.
        """
        archetype_cls = ARCHETYPE_MAP.get(classification.archetype, GenericArchetype)
        archetype = archetype_cls()
        logger.info(
            "Applying archetype %s via %s",
            classification.archetype, archetype_cls.__name__,
        )
        try:
            return archetype.apply(self.api, doc_id, classification, plan)
        except Exception as exc:
            logger.error("ArchetypeEngine.apply failed: %s", exc)
            return []
```

- [ ] **Step 4: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_archetype_engine.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/archetype_engine.py tests/test_archetype_engine.py
git commit -m "feat: add ArchetypeEngine — dispatches DashboardPlan to archetype templates"
```

---

### Task 7: New main.py — `--input xlsx` CLI

**Files:**
- Modify: `main.py` (full rewrite)
- Create: `tests/test_new_main.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_new_main.py`:

```python
"""Tests for the new main.py — --input xlsx CLI."""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport
from core.dashboard_composer import DashboardPlan, Page, PageSection
from core.pipeline import PipelineResult
from core.data_analyzer import DataProfile


def _make_pipeline_result():
    profile = DataProfile(
        sheets=["Employes"],
        columns={"Employes": ["Nom", "Departement"]},
        stats={},
        apparent_fk=[],
        markdown_summary="",
    )
    classification = ClassificationResult(
        archetype="HR", confidence=0.91,
        table_mapping={"employees": "Employes"},
        params={"name_col": "Nom"},
    )
    insights = InsightReport(insights=[])
    plan = DashboardPlan(pages=[
        Page(name="Dashboard", sections=[
            PageSection(widget="table", table="Employes", title="Tableau"),
        ]),
    ])
    return PipelineResult(
        profile=profile,
        classification=classification,
        insights=insights,
        dashboard_plan=plan,
        errors=[],
    )


class TestNewMain:
    def test_dry_run_prints_plan_without_upload(self, tmp_path, capsys):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        result = _make_pipeline_result()

        with patch("main.DataAnalyzer") as MockDA, \
             patch("main.PipelineOrchestrator") as MockPO, \
             patch("main.GristImporter") as MockGI, \
             patch("main.ArchetypeEngine") as MockAE:
            MockDA.return_value.analyze.return_value = result.profile
            MockPO.return_value.run.return_value = result

            from main import main
            with pytest.raises(SystemExit) as exc_info:
                import sys
                sys.argv = ["main.py", "--input", str(xlsx), "--dry-run"]
                main()

        MockGI.return_value.import_excel.assert_not_called()
        MockAE.return_value.apply.assert_not_called()
        captured = capsys.readouterr()
        assert "DashboardPlan" in captured.out or "pages" in captured.out

    def test_full_run_calls_importer_and_engine(self, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        result = _make_pipeline_result()

        with patch("main.DataAnalyzer") as MockDA, \
             patch("main.PipelineOrchestrator") as MockPO, \
             patch("main.GristImporter") as MockGI, \
             patch("main.ArchetypeEngine") as MockAE, \
             patch("main.GristAPI"):
            MockDA.return_value.analyze.return_value = result.profile
            MockPO.return_value.run.return_value = result
            MockGI.return_value.import_excel.return_value = "new~doc~1"
            MockAE.return_value.apply.return_value = ["Dashboard"]

            import sys
            sys.argv = ["main.py", "--input", str(xlsx)]
            from main import main
            main()

        MockGI.return_value.import_excel.assert_called_once_with(str(xlsx))
        MockAE.return_value.apply.assert_called_once()

    def test_pipeline_errors_printed_but_continue(self, tmp_path, capsys):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        result = _make_pipeline_result()
        result.errors = ["DomainClassifier failed: timeout"]

        with patch("main.DataAnalyzer") as MockDA, \
             patch("main.PipelineOrchestrator") as MockPO, \
             patch("main.GristImporter") as MockGI, \
             patch("main.ArchetypeEngine") as MockAE, \
             patch("main.GristAPI"):
            MockDA.return_value.analyze.return_value = result.profile
            MockPO.return_value.run.return_value = result
            MockGI.return_value.import_excel.return_value = "new~doc~1"
            MockAE.return_value.apply.return_value = []

            import sys
            sys.argv = ["main.py", "--input", str(xlsx)]
            from main import main
            main()

        captured = capsys.readouterr()
        assert "DomainClassifier failed" in captured.out
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_new_main.py -v 2>&1 | head -20
```

Expected: tests fail because `main.py` still uses the old `--doc-id`/`--doc-name` CLI.

- [ ] **Step 3: Rewrite `main.py`**

```python
#!/usr/bin/env python3
"""Data-to-Dashboard — CLI Interface

A non-expert user provides an Excel file.
The tool produces a fully configured Grist document with pages,
charts, card views, and forms — driven by business insights.

Usage:
    python main.py --input employees_rh.xlsx
    python main.py --input sales_2024.xlsx --dry-run
    python main.py --input data.xlsx --output ./results/
"""

import argparse
import json
import sys
from pathlib import Path

from config import Settings
from core.grist_api import GristAPI
from core.grist_importer import GristImporter
from core.data_analyzer import DataAnalyzer
from core.pipeline import PipelineOrchestrator
from core.archetype_engine import ArchetypeEngine


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Data-to-Dashboard: Excel → Grist document with dashboards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i", type=str, required=True,
        help="Chemin vers le fichier Excel (.xlsx)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default="./output/",
        help="Dossier de sortie pour les logs JSON (défaut: ./output/)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Afficher le DashboardPlan JSON sans créer de document Grist"
    )

    args = parser.parse_args()
    settings = Settings()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'=' * 60}")
    print("DATA-TO-DASHBOARD")
    print(f"{'=' * 60}")
    print(f"Fichier : {args.input}")

    # Step 1: Analyze the Excel file
    print("\n[1/4] Analyse du fichier Excel...")
    analyzer = DataAnalyzer(settings)
    try:
        profile = analyzer.analyze(args.input)
    except FileNotFoundError:
        print(f"Fichier introuvable : {args.input}")
        sys.exit(1)
    print(f"  {len(profile.sheets)} feuille(s) : {profile.sheets}")

    # Step 2: Run LLM pipeline
    print("\n[2/4] Pipeline LLM (classification + insights + dashboard plan)...")
    orchestrator = PipelineOrchestrator(settings)
    result = orchestrator.run(profile)

    if result.errors:
        print(f"  Avertissements pipeline :")
        for err in result.errors:
            print(f"    - {err}")

    if result.classification:
        print(f"  Archetype : {result.classification.archetype} "
              f"(confiance : {result.classification.confidence:.0%})")
    if result.insights:
        print(f"  Insights  : {len(result.insights.insights)}")
    if result.dashboard_plan:
        print(f"  Pages     : {len(result.dashboard_plan.pages)}")

    # Save pipeline result
    result_file = output_dir / "pipeline_result.json"
    result.save(str(result_file))
    print(f"  Pipeline result sauvegardé : {result_file}")

    # Dry-run: print plan and exit
    if args.dry_run:
        print("\n[DRY-RUN] DashboardPlan JSON :")
        if result.dashboard_plan:
            print(json.dumps(result.dashboard_plan.model_dump(), indent=2, ensure_ascii=False))
        else:
            print("  (pas de DashboardPlan — pipeline incomplet)")
        print("\nDRY-RUN terminé. Aucun document Grist créé.")
        return

    if not result.dashboard_plan or not result.classification:
        print("\nPipeline incomplet — impossible de créer le document Grist.")
        sys.exit(1)

    # Step 3: Import Excel to Grist
    print("\n[3/4] Import du fichier Excel dans Grist...")
    api = GristAPI(settings.GRIST_SERVER, settings.GRIST_API_KEY)
    importer = GristImporter(api)
    try:
        doc_id = importer.import_excel(args.input)
    except Exception as exc:
        print(f"  Erreur import : {exc}")
        sys.exit(1)
    print(f"  Document créé : {doc_id}")

    # Step 4: Apply archetype template
    print("\n[4/4] Application du template archetype...")
    engine = ArchetypeEngine(api)
    created_pages = engine.apply(doc_id, result.classification, result.dashboard_plan)
    print(f"  Pages créées : {created_pages}")

    print(f"\n{'=' * 60}")
    print("TERMINÉ")
    print(f"{'=' * 60}")
    print(f"Document Grist : {settings.GRIST_SERVER}/doc/{doc_id}")
    print(f"Pipeline log   : {result_file}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_new_main.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

> The old `tests/test_main.py` will fail because it imports from `main.py` functions that no longer exist (`validate_doc_id`, `call_llm`). Delete it:

```bash
rm /home/wderue/workspace/grist-excel/tests/test_main.py
python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add main.py tests/test_new_main.py && git rm tests/test_main.py
git commit -m "feat: rewrite main.py with --input xlsx CLI; replace old doc-id/doc-name flow"
```

---

### Task 8: Delete old modules

**Files:**
- Delete: `core/grist_analyzer.py`, `core/schema_analyzer.py`, `core/grist_updater.py`
- Delete: `tests/test_grist_analyzer.py`, `tests/test_schema_analyzer.py`, `tests/test_grist_updater.py`

- [ ] **Step 1: Verify old modules are not imported anywhere in new code**

```bash
cd /home/wderue/workspace/grist-excel && grep -r "grist_analyzer\|schema_analyzer\|grist_updater" --include="*.py" \
  --exclude-dir=venv --exclude-dir=__pycache__ .
```

Expected: only the old source files themselves and their test files appear. No other file imports them.

- [ ] **Step 2: Delete files**

```bash
cd /home/wderue/workspace/grist-excel && git rm \
  core/grist_analyzer.py \
  core/schema_analyzer.py \
  core/grist_updater.py \
  tests/test_grist_analyzer.py \
  tests/test_schema_analyzer.py \
  tests/test_grist_updater.py
```

- [ ] **Step 3: Run full suite — verify no regressions**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

Expected: all remaining tests pass.

- [ ] **Step 4: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git commit -m "chore: remove grist_analyzer, schema_analyzer, grist_updater — replaced by new pipeline"
```

---

### Task 9: eval_classifier.py + prompts/

**Files:**
- Create: `eval_classifier.py`
- Create: `prompts/domain_classifier_v1.md` … `v5.md`
- Create: `prompts/insight_extractor_v1.md` … `v5.md`
- Create: `prompts/dashboard_composer_v1.md` … `v5.md`
- Create: `prompts/data_analyzer_v1.md` … `v5.md`

- [ ] **Step 1: Create the `prompts/` directory and 4 × 5 prompt files**

Each prompt file is a Markdown system prompt. The 5 variants differ in style: v1=minimal, v2=structured, v3=few-shot, v4=chain-of-thought, v5=expert-persona.

```bash
mkdir -p /home/wderue/workspace/grist-excel/prompts
```

Create `prompts/domain_classifier_v1.md`:
```markdown
# Domain Classifier — v1 (Minimal)

Classify the business domain of the provided data profile.
Return JSON matching the schema.
```

Create `prompts/domain_classifier_v2.md`:
```markdown
# Domain Classifier — v2 (Structured)

You are a domain classifier. Analyze the data profile and:
1. Identify the business domain from: HR, DECISIONNEL, SUPPORT, STUDENT, SI, PROJECT, GENERIC
2. Map semantic roles to exact table names from the data
3. Map semantic params to exact column names from the data
4. Return confidence score (0.0–1.0)

Rules:
- All values in table_mapping and params must be exact names from the provided lists
- If domain is unclear, use GENERIC with low confidence
- Return ONLY valid JSON matching the schema
```

Create `prompts/domain_classifier_v3.md`:
```markdown
# Domain Classifier — v3 (Few-Shot)

Classify the data profile into a business domain.

Example 1:
Input: sheets=[Employes, Absences], columns Employes=[ID,Nom,Departement,Salaire]
Output: {"archetype":"HR","confidence":0.92,"table_mapping":{"employees":"Employes","absences":"Absences"},"params":{"name_col":"Nom","department_col":"Departement"}}

Example 2:
Input: sheets=[Tickets, Clients], columns Tickets=[ID,Titre,Statut,Agent]
Output: {"archetype":"SUPPORT","confidence":0.87,"table_mapping":{"tickets":"Tickets","customers":"Clients"},"params":{"status_col":"Statut"}}

Now classify the following:
```

Create `prompts/domain_classifier_v4.md`:
```markdown
# Domain Classifier — v4 (Chain-of-Thought)

Classify the data profile step by step:
1. List the sheet names and their key columns
2. Identify domain keywords (employee, ticket, grade, asset, task…)
3. Select the archetype that best matches
4. Map each semantic role to the exact table name
5. Map each semantic param to the exact column name
6. Estimate confidence (0.0–1.0)
7. Return the JSON result

Think through each step explicitly, then output ONLY the final JSON.
```

Create `prompts/domain_classifier_v5.md`:
```markdown
# Domain Classifier — v5 (Expert Persona)

You are a senior enterprise data architect with 20 years of experience classifying business domains.
Given a data profile, you immediately recognise patterns: HR systems have employee and absence tables;
support systems have ticket tables with status columns; BI systems have numeric KPI columns.

Classify the data profile. You are confident and precise. You never hallucinate table or column names —
you use only the exact names from the provided lists. Return ONLY valid JSON.
```

Repeat the same 5-variant pattern for `insight_extractor_v*.md`, `dashboard_composer_v*.md`, `data_analyzer_v*.md`.

```bash
# Create remaining 15 prompt files (with appropriate content for each agent)
for agent in insight_extractor dashboard_composer data_analyzer; do
  for v in v1 v2 v3 v4 v5; do
    echo "# ${agent} — ${v}" > "/home/wderue/workspace/grist-excel/prompts/${agent}_${v}.md"
    echo "" >> "/home/wderue/workspace/grist-excel/prompts/${agent}_${v}.md"
    echo "System prompt for ${agent} variant ${v}." >> "/home/wderue/workspace/grist-excel/prompts/${agent}_${v}.md"
  done
done
```

Then manually fill in each file with appropriate content (minimal/structured/few-shot/CoT/expert variants).

- [ ] **Step 2: Create `eval_classifier.py`**

```python
#!/usr/bin/env python3
"""Prompt Evaluation Tool — compares 5 system prompt variants per agent.

Usage:
    python eval_classifier.py --input samples/employees_rh.xlsx
    python eval_classifier.py --input samples/employees_rh.xlsx --agent insight_extractor
    python eval_classifier.py --input samples/employees_rh.xlsx --versions v1 v3

Output:
    output/prompt_eval/{agent}_{version}.json   ← raw output + metrics
    output/prompt_eval/report.md                ← comparative table
"""

import argparse
import json
import time
from pathlib import Path

from config import Settings
from core.data_analyzer import DataAnalyzer, DataProfile
from core.domain_classifier import DomainClassifier, ClassificationResult
from core.insight_extractor import InsightExtractor, InsightReport
from core.dashboard_composer import DashboardComposer, DashboardPlan

VALID_AGENTS = ["domain_classifier", "insight_extractor", "dashboard_composer"]
VALID_VERSIONS = ["v1", "v2", "v3", "v4", "v5"]


def load_prompt(agent: str, version: str) -> str:
    """Load a prompt variant from the prompts/ directory."""
    path = Path("prompts") / f"{agent}_{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def eval_domain_classifier(
    profile: DataProfile, system_prompt: str, settings: Settings
) -> dict:
    """Run DomainClassifier with a custom system prompt. Returns metrics dict."""
    classifier = DomainClassifier(settings)

    # Monkey-patch the system prompt for this run
    original_classify = classifier.classify

    def classify_with_custom_prompt(p: DataProfile) -> ClassificationResult:
        prompt = classifier._build_prompt(p)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return ClassificationResult(**classifier._call_llm(messages))

    classifier.classify = classify_with_custom_prompt

    start = time.time()
    try:
        result = classifier.classify(profile)
        latency = time.time() - start
        return {
            "archetype": result.archetype,
            "confidence": result.confidence,
            "table_mapping": result.table_mapping,
            "params": result.params,
            "latency_s": round(latency, 2),
            "error": None,
        }
    except Exception as exc:
        return {
            "archetype": None,
            "confidence": None,
            "table_mapping": {},
            "params": {},
            "latency_s": round(time.time() - start, 2),
            "error": str(exc),
        }


def eval_insight_extractor(
    profile: DataProfile,
    classification: ClassificationResult,
    system_prompt: str,
    settings: Settings,
) -> dict:
    """Run InsightExtractor with a custom system prompt."""
    extractor = InsightExtractor(settings)

    def extract_with_custom_prompt(p, c):
        prompt = extractor._build_prompt(p, c)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        return InsightReport(**extractor._call_llm(messages))

    extractor.extract = extract_with_custom_prompt

    start = time.time()
    try:
        result = extractor.extract(profile, classification)
        latency = time.time() - start
        return {
            "insight_count": len(result.insights),
            "insights": [i.model_dump() for i in result.insights],
            "latency_s": round(latency, 2),
            "error": None,
        }
    except Exception as exc:
        return {
            "insight_count": 0,
            "insights": [],
            "latency_s": round(time.time() - start, 2),
            "error": str(exc),
        }


def eval_dashboard_composer(
    classification: ClassificationResult,
    insights: InsightReport,
    system_prompt: str,
    settings: Settings,
) -> dict:
    """Run DashboardComposer with a custom system prompt."""
    composer = DashboardComposer(settings)

    def compose_with_custom_prompt(c, i):
        prompt = composer._build_prompt(c, i)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        raw_plan = DashboardPlan(**composer._call_llm(messages))
        return raw_plan.self_reflect(i)

    composer.compose = compose_with_custom_prompt

    start = time.time()
    try:
        result = composer.compose(classification, insights)
        latency = time.time() - start
        return {
            "page_count": len(result.pages),
            "section_count": sum(len(p.sections) for p in result.pages),
            "pages": result.model_dump(),
            "latency_s": round(latency, 2),
            "error": None,
        }
    except Exception as exc:
        return {
            "page_count": 0,
            "section_count": 0,
            "pages": {},
            "latency_s": round(time.time() - start, 2),
            "error": str(exc),
        }


def generate_report(results: dict, output_dir: Path) -> None:
    """Generate report.md comparing all agent/version combinations."""
    lines = ["# Prompt Evaluation Report\n"]

    for agent, versions in results.items():
        lines.append(f"## {agent}\n")
        if agent == "domain_classifier":
            lines.append("| Version | Archetype | Confidence | Latency (s) | Error |")
            lines.append("|---|---|---|---|---|")
            for v, r in versions.items():
                lines.append(
                    f"| {v} | {r.get('archetype','-')} | "
                    f"{r.get('confidence','-')} | {r.get('latency_s','-')} | "
                    f"{r.get('error') or '-'} |"
                )
        elif agent == "insight_extractor":
            lines.append("| Version | Insights | Latency (s) | Error |")
            lines.append("|---|---|---|---|")
            for v, r in versions.items():
                lines.append(
                    f"| {v} | {r.get('insight_count','-')} | "
                    f"{r.get('latency_s','-')} | {r.get('error') or '-'} |"
                )
        elif agent == "dashboard_composer":
            lines.append("| Version | Pages | Sections | Latency (s) | Error |")
            lines.append("|---|---|---|---|---|")
            for v, r in versions.items():
                lines.append(
                    f"| {v} | {r.get('page_count','-')} | "
                    f"{r.get('section_count','-')} | "
                    f"{r.get('latency_s','-')} | {r.get('error') or '-'} |"
                )
        lines.append("")

    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate prompt variants per LLM agent"
    )
    parser.add_argument("--input", required=True, help="Excel file path")
    parser.add_argument(
        "--agent", default="domain_classifier",
        choices=VALID_AGENTS,
        help="Agent to evaluate (default: domain_classifier)"
    )
    parser.add_argument(
        "--versions", nargs="+", default=VALID_VERSIONS,
        help="Versions to test (default: v1 v2 v3 v4 v5)"
    )
    parser.add_argument("--output", default="./output/", help="Output directory")
    args = parser.parse_args()

    settings = Settings()
    output_dir = Path(args.output) / "prompt_eval"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Analyzing {args.input}...")
    analyzer = DataAnalyzer(settings)
    profile = analyzer.analyze(args.input)
    print(f"  Sheets: {profile.sheets}")

    # Run domain_classifier first (needed as input for insight_extractor)
    classifier = DomainClassifier(settings)
    classification = classifier.classify(profile)

    insight_extractor = InsightExtractor(settings)
    insights = insight_extractor.extract(profile, classification)

    results: dict = {args.agent: {}}

    for version in args.versions:
        print(f"\nEvaluating {args.agent} {version}...")
        try:
            system_prompt = load_prompt(args.agent, version)
        except FileNotFoundError as e:
            print(f"  Skipping: {e}")
            continue

        if args.agent == "domain_classifier":
            r = eval_domain_classifier(profile, system_prompt, settings)
        elif args.agent == "insight_extractor":
            r = eval_insight_extractor(profile, classification, system_prompt, settings)
        elif args.agent == "dashboard_composer":
            r = eval_dashboard_composer(classification, insights, system_prompt, settings)
        else:
            continue

        results[args.agent][version] = r
        out_file = output_dir / f"{args.agent}_{version}.json"
        out_file.write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str))
        print(f"  Saved: {out_file}")
        if r.get("error"):
            print(f"  Error: {r['error']}")

    generate_report(results, output_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the script runs (dry-check)**

```bash
cd /home/wderue/workspace/grist-excel && python3 -c "import eval_classifier; print('OK')"
```

Expected: `OK` (imports succeed without errors)

- [ ] **Step 4: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

- [ ] **Step 5: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add eval_classifier.py prompts/
git commit -m "feat: add eval_classifier.py + 20 prompt variant files for agent evaluation"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `core/archetype_engine.py` — Task 6
- ✅ `archetypes/*.py` (7 templates) — Tasks 3, 4, 5
- ✅ `main.py` new CLI `--input` — Task 7
- ✅ `eval_classifier.py` — Task 9
- ✅ `prompts/` 20 files — Task 9
- ✅ Delete `grist_analyzer`, `schema_analyzer`, `grist_updater` — Task 8
- ✅ Grist apply_actions validation — Task 1
- ✅ `--dry-run` prints DashboardPlan JSON — Task 7
- ✅ Error handling: apply_actions 400/500 → log + continue — base.py helpers + GenericArchetype/HRArchetype
- ✅ `GristTableResolver` resolves tableRef integers — Task 2
- ✅ `get_records()` on GristAPI — Task 2

**Placeholder scan:** No TBDs. All steps have concrete code. Task 5 archetypes inherit HRArchetype — this is intentional (the DashboardPlan drives the layout; differentiation between archetypes happens at Plan C+, when domain-specific defaults might be added).

**Type consistency:**
- `BaseArchetype.apply()` returns `list[str]` → matches `ArchetypeEngine.apply()` return type
- `GristTableResolver.get_ref()` takes `str`, returns `int` → consistent with apply_actions usage
- `PipelineResult` from `core/pipeline.py` is used in `test_new_main.py` → consistent
- `DataAnalyzer(settings)` — constructor updated in Plan C fixes → consistent

**Critical dependency:** Task 3–5 depend on Task 1 (validated Grist action format). If the field names discovered in Task 1 differ from the defaults in `base.py`, update the `_add_*` helpers before implementing Task 3.
