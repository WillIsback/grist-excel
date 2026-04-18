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

    def _add_table_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> None:
        """Add a table (grid) section to an existing page."""
        api.apply_actions(doc_id, [
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

    def _add_card_list_section(
        self,
        api: GristAPI,
        doc_id: str,
        view_id: int,
        table_ref: int,
        title: str = "",
    ) -> None:
        """Add a card list (detail) section to an existing page."""
        api.apply_actions(doc_id, [
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
