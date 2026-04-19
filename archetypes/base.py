"""Base archetype interface and shared utilities.

GristTableResolver: resolves string tableId → integer tableRef
BaseArchetype: abstract base class all archetype modules implement
"""

from __future__ import annotations

import json
import unicodedata
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan

if TYPE_CHECKING:
    from core.visual_intents import VisualIntent, VisualIntentPlan


OFFICIAL_WIDGET_IDS = {
    "advanced_chart": "@gristlabs/widget-chart",
    "markdown": "@gristlabs/widget-markdown",
    "map": "@gristlabs/widget-map#map",
    "jupyterlite": "@gristlabs/widget-jupyterlite",
}


def _normalize(text: str) -> str:
    """Normalize text for comparison (remove accents, lowercase)."""
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()


class GristTableResolver:
    """Resolves string tableId → integer tableRef for apply_actions calls.

    Queries _grist_Tables once at construction; subsequent look-ups are O(1).
    Supports accent-insensitive and case-insensitive matching.
    """

    def __init__(self, api: GristAPI, doc_id: str):
        records = api.get_records(doc_id, "_grist_Tables")
        self._map: dict[str, int] = {
            r["fields"]["tableId"]: r["id"]
            for r in records
            if "tableId" in r.get("fields", {})
        }
        # Build accent-insensitive lookup
        self._norm_map: dict[str, str] = {}
        for table_id in self._map:
            norm = _normalize(table_id)
            self._norm_map[norm] = table_id

    def get_ref(self, table_id: str) -> int:
        """Return the integer tableRef for a tableId string.

        Supports exact match, case-insensitive match, and accent-insensitive match.
        Raises:
            KeyError: If table_id is not found in the document.
        """
        # Direct lookup
        if table_id in self._map:
            return self._map[table_id]

        # Accent/case-insensitive lookup
        norm_key = _normalize(table_id)
        for norm, actual in self._norm_map.items():
            if norm == norm_key:
                return self._map[actual]

        available = list(self._map.keys())
        raise KeyError(
            f"Table '{table_id}' not found. Available: {available}"
        )


class BaseArchetype(ABC):
    """Abstract base for all archetype templates."""

    @abstractmethod
    def apply(
        self,
        api: GristAPI,
        doc_id: str,
        classification: ClassificationResult,
        plan: DashboardPlan,
        visual_intents: "VisualIntentPlan | None" = None,
    ) -> list[str]:
        """Apply the archetype template to the Grist document.

        Returns:
            List of created page names.
        """

    # ------------------------------------------------------------------
    # Shared helpers — use validated Grist action format from Task 1
    # ------------------------------------------------------------------

    def _create_page(self, api: GristAPI, doc_id: str, name: str) -> int:
        """Create a page (view) visible in the Grist UI. Returns viewId.

        Requires three entries: _grist_Views + _grist_TabBar + _grist_Pages.
        """
        result = api.apply_actions(doc_id, [
            ["AddRecord", "_grist_Views", None, {"name": name, "type": "raw_data"}],
        ])
        view_id: int = result["retValues"][0]
        api.apply_actions(doc_id, [
            ["AddRecord", "_grist_TabBar", None, {"viewRef": view_id, "tabPos": view_id}],
            ["AddRecord", "_grist_Pages",  None, {"viewRef": view_id, "indentation": 0, "pagePos": view_id}],
        ])
        return view_id

    def _get_col_ref_map(self, api: GristAPI, doc_id: str, table_ref: int) -> dict[str, int]:
        """Return {colId: colRef} for user columns in a table (excludes manualSort)."""
        records = api.get_records(doc_id, "_grist_Tables_column")
        return {
            r["fields"]["colId"]: r["id"]
            for r in records
            if r["fields"].get("parentId") == table_ref
            and r["fields"].get("colId")
            and not r["fields"]["colId"].startswith("manualSort")
        }

    def _add_section_fields(
        self,
        api: GristAPI,
        doc_id: str,
        section_id: int,
        col_refs: list[int],
    ) -> None:
        """Add _grist_Views_section_field records to make a section show its columns."""
        if not col_refs:
            return
        actions = [
            ["AddRecord", "_grist_Views_section_field", None, {
                "parentId": section_id,
                "colRef": ref,
            }]
            for ref in col_refs
        ]
        api.apply_actions(doc_id, actions)

    def _add_table_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> int:
        """Add a table (grid) section to an existing page. Returns section_id."""
        result = api.apply_actions(doc_id, [
            ["AddRecord", "_grist_Views_section", None, {
                "tableRef": table_ref,
                "parentId": view_id,
                "parentKey": "record",
                "title": title,
                "defaultWidth": 100,
                "borderWidth": 1,
                "chartType": "",
                "sortColRefs": "[]",
                "linkSrcSectionRef": 0,
                "linkSrcColRef": 0,
                "linkTargetColRef": 0,
            }],
        ])
        section_id: int = result["retValues"][0]
        col_refs = list(self._get_col_ref_map(api, doc_id, table_ref).values())
        self._add_section_fields(api, doc_id, section_id, col_refs)
        return section_id

    def _add_chart_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        chart_type: str,
        title: str,
        x_col: str | None = None,
        y_col: str | None = None,
    ) -> int:
        """Add a chart section to an existing page. Returns section_id.

        x_col and y_col are Grist colId strings. x is added first (grouping axis),
        y second (value axis). Falls back to all cols if unresolved.
        """
        result = api.apply_actions(doc_id, [
            ["AddRecord", "_grist_Views_section", None, {
                "tableRef": table_ref,
                "parentId": view_id,
                "parentKey": "chart",
                "chartType": chart_type,
                "title": title,
                "defaultWidth": 100,
                "borderWidth": 1,
                "sortColRefs": "[]",
                "linkSrcSectionRef": 0,
                "linkSrcColRef": 0,
                "linkTargetColRef": 0,
            }],
        ])
        section_id: int = result["retValues"][0]
        col_map = self._get_col_ref_map(api, doc_id, table_ref)
        # Resolve x/y by exact match then accent-normalized fallback
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
            # Fallback: first 2 cols only — avoids polluting chart with irrelevant fields
            col_refs = list(col_map.values())[:2]

        self._add_section_fields(api, doc_id, section_id, col_refs)
        return section_id

    def _add_card_list_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> int:
        """Add a card list (detail) section to an existing page. Returns section_id."""
        result = api.apply_actions(doc_id, [
            ["AddRecord", "_grist_Views_section", None, {
                "tableRef": table_ref,
                "parentId": view_id,
                "parentKey": "detail",
                "title": title,
                "defaultWidth": 100,
                "borderWidth": 1,
                "chartType": "",
                "sortColRefs": "[]",
                "linkSrcSectionRef": 0,
                "linkSrcColRef": 0,
                "linkTargetColRef": 0,
            }],
        ])
        section_id: int = result["retValues"][0]
        col_refs = list(self._get_col_ref_map(api, doc_id, table_ref).values())
        self._add_section_fields(api, doc_id, section_id, col_refs)
        return section_id

    def _add_form_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> int:
        """Add a form section to an existing page. Returns section_id."""
        result = api.apply_actions(doc_id, [
            ["AddRecord", "_grist_Views_section", None, {
                "tableRef": table_ref,
                "parentId": view_id,
                "parentKey": "form",
                "title": title,
                "defaultWidth": 100,
                "borderWidth": 1,
                "chartType": "",
                "sortColRefs": "[]",
                "linkSrcSectionRef": 0,
                "linkSrcColRef": 0,
                "linkTargetColRef": 0,
            }],
        ])
        section_id: int = result["retValues"][0]
        col_refs = list(self._get_col_ref_map(api, doc_id, table_ref).values())
        self._add_section_fields(api, doc_id, section_id, col_refs)
        return section_id

    def _add_custom_widget_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str,
        widget_def: dict,
        *,
        access: str = "none",
        widget_options: dict | None = None,
        columns_mapping: dict[str, str] | None = None,
    ) -> int:
        """Add a Grist custom section backed by an official widget definition."""
        col_ref_map = self._get_col_ref_map(api, doc_id, table_ref)
        persisted_columns_mapping = None
        if columns_mapping:
            persisted_columns_mapping = {
                widget_column: col_ref_map[column_id]
                for widget_column, column_id in columns_mapping.items()
                if column_id in col_ref_map
            }
        custom_view = {
            "mode": "url",
            "url": None,
            "widgetId": widget_def.get("widgetId"),
            "widgetDef": widget_def,
            "widgetOptions": widget_options,
            "columnsMapping": persisted_columns_mapping,
            "access": access,
            "pluginId": widget_def.get("source", {}).get("pluginId", ""),
            "sectionId": "",
            "renderAfterReady": widget_def.get("renderAfterReady", False),
        }
        options = json.dumps(
            {"customView": json.dumps(custom_view, ensure_ascii=False)},
            ensure_ascii=False,
        )
        result = api.apply_actions(doc_id, [["AddRecord", "_grist_Views_section", None, {
            "tableRef": table_ref,
            "parentId": view_id,
            "parentKey": "custom",
            "title": title,
            "defaultWidth": 100,
            "borderWidth": 1,
            "options": options,
            "chartType": "",
            "sortColRefs": "[]",
            "linkSrcSectionRef": 0,
            "linkSrcColRef": 0,
            "linkTargetColRef": 0,
        }]])
        section_id: int = result["retValues"][0]
        col_refs = list(col_ref_map.values())
        self._add_section_fields(api, doc_id, section_id, col_refs)
        return section_id

    def _target_page_for_promoted_intent(self, intent: "VisualIntent") -> str | None:
        """Return the page name that should host the promoted official widget."""
        if intent.kind == "cross_tab":
            return "Syntheses croisees"
        return None

    def _maybe_add_promoted_widget(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        page_name: str,
        rendered_tables: dict[str, int],
        visual_intents: "VisualIntentPlan | None",
    ) -> bool:
        """Materialize one promoted official Grist widget when safely supported."""
        if visual_intents is None:
            return False

        promoted_intent = visual_intents.get_promoted_intent()
        promoted_widget = visual_intents.get_promoted_widget()
        if promoted_intent is None or promoted_widget != "advanced_chart":
            return False

        target_page = self._target_page_for_promoted_intent(promoted_intent)
        if target_page is not None and _normalize(page_name) != _normalize(target_page):
            return False

        table_ref = rendered_tables.get(promoted_intent.source_table)
        if table_ref is None:
            return False

        widget_id = OFFICIAL_WIDGET_IDS[promoted_widget]
        widget_def = api.get_widget(widget_id)
        if not widget_def:
            return False

        title = f"{promoted_intent.title} - widget avance"
        self._add_custom_widget_section(
            api,
            doc_id,
            view_id,
            table_ref,
            title,
            widget_def,
        )
        return True

    def _create_text_table(
        self,
        api: GristAPI,
        doc_id: str,
        table_id: str,
        column_id: str,
        content: str,
    ) -> None:
        """Create a minimal text table used to back narrative widgets."""
        api.create_table(doc_id, table_id, columns=[
            {"id": column_id, "fields": {"type": "Text"}},
        ])
        api.add_records(doc_id, table_id, [{column_id: content}])

    def _hide_backing_table_page(self, api: GristAPI, doc_id: str, table_id: str) -> None:
        """Remove the auto-created raw page for a backing table, keeping the table intact."""
        try:
            views = api.get_records(doc_id, "_grist_Views")
            pages = api.get_records(doc_id, "_grist_Pages")
            tabs = api.get_records(doc_id, "_grist_TabBar")
            target_view_ids = {
                v["id"] for v in views if v.get("fields", {}).get("name") == table_id
            }
            if not target_view_ids:
                return
            actions = []
            for page in pages:
                if page.get("fields", {}).get("viewRef") in target_view_ids:
                    actions.append(["RemoveRecord", "_grist_Pages", page["id"]])
            for tab in tabs:
                if tab.get("fields", {}).get("viewRef") in target_view_ids:
                    actions.append(["RemoveRecord", "_grist_TabBar", tab["id"]])
            if actions:
                api.apply_actions(doc_id, actions)
        except Exception:
            pass  # non-fatal: cosmetic cleanup only

    def _add_geo_widget_page(
        self,
        api: GristAPI,
        doc_id: str,
        resolver: GristTableResolver,
        intent: "VisualIntent",
    ) -> str | None:
        table_ref = resolver.get_ref(intent.source_table)
        widget_def = api.get_widget(OFFICIAL_WIDGET_IDS["map"])
        if not widget_def:
            return None

        view_id = self._create_page(api, doc_id, intent.title)
        self._add_custom_widget_section(
            api,
            doc_id,
            view_id,
            table_ref,
            intent.title,
            widget_def,
            access=intent.metadata.get("access", "read table"),
            columns_mapping=intent.metadata.get("columns_mapping"),
        )
        return intent.title

    def _add_markdown_widget_page(
        self,
        api: GristAPI,
        doc_id: str,
        resolver: GristTableResolver,
        intent: "VisualIntent",
    ) -> str | None:
        content = (intent.narrative or "").strip()
        if not content:
            return None

        table_id = intent.metadata.get("table_name", "Narrative_Summary")
        column_id = intent.metadata.get("content_column", "Content")
        self._create_text_table(api, doc_id, table_id, column_id, content)
        self._hide_backing_table_page(api, doc_id, table_id)
        fresh_resolver = GristTableResolver(api, doc_id)
        table_ref = fresh_resolver.get_ref(table_id)
        widget_def = api.get_widget(OFFICIAL_WIDGET_IDS["markdown"])
        if not widget_def:
            return None

        page_name = intent.title
        view_id = self._create_page(api, doc_id, page_name)
        self._add_custom_widget_section(
            api,
            doc_id,
            view_id,
            table_ref,
            page_name,
            widget_def,
            access="full",
            columns_mapping={"Content": column_id},
        )
        return page_name

    def _materialize_additional_visual_widgets(
        self,
        api: GristAPI,
        doc_id: str,
        resolver: GristTableResolver,
        visual_intents: "VisualIntentPlan | None",
    ) -> list[str]:
        """Create deterministic extra pages for official widgets beyond the promoted one."""
        if visual_intents is None:
            return []

        created_pages: list[str] = []
        for intent in visual_intents.intents:
            try:
                if intent.preferred_widget == "map":
                    page_name = self._add_geo_widget_page(api, doc_id, resolver, intent)
                elif intent.preferred_widget == "markdown":
                    page_name = self._add_markdown_widget_page(api, doc_id, resolver, intent)
                else:
                    page_name = None
            except Exception:
                page_name = None
            if page_name:
                created_pages.append(page_name)
        return created_pages
