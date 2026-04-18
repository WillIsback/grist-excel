"""GENERIC archetype — fallback for unrecognised business domains.

Renders every page and section from the DashboardPlan as-is.
Skips any section whose table cannot be resolved, with a warning log.
"""

from __future__ import annotations
import logging
from archetypes.base import BaseArchetype, GristTableResolver
from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan

logger = logging.getLogger(__name__)

WIDGET_TO_HELPER = {
    "table":     "_add_table_section",
    "card_list": "_add_card_list_section",
    "card":      "_add_card_list_section",
    "form":      "_add_form_section",
}


class GenericArchetype(BaseArchetype):
    """GENERIC archetype: renders DashboardPlan pages as-is."""

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
                if not section.table:
                    continue
                try:
                    table_ref = resolver.get_ref(section.table)
                except KeyError:
                    logger.warning(
                        "Table '%s' not in doc — skipping section '%s'",
                        section.table, section.title,
                    )
                    continue
                try:
                    if section.widget == "chart" and section.chart_type:
                        self._add_chart_section(
                            api, doc_id, view_id, table_ref,
                            section.chart_type, section.title or "",
                        )
                    else:
                        helper = WIDGET_TO_HELPER.get(section.widget)
                        if helper:
                            getattr(self, helper)(
                                api, doc_id, view_id, table_ref,
                                section.title or "",
                            )
                except Exception as exc:
                    logger.error(
                        "Section '%s' failed: %s — continuing", section.title, exc,
                    )

            created_pages.append(page.name)

        return created_pages
