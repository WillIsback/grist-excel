"""Base archetype interface and shared utilities.

GristTableResolver: resolves string tableId → integer tableRef
BaseArchetype: abstract base class all archetype modules implement
"""

from __future__ import annotations

import unicodedata
from abc import ABC, abstractmethod

from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan


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
