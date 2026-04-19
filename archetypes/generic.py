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
from core.visual_intents import VisualIntentPlan

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
        visual_intents: VisualIntentPlan | None = None,
    ) -> list[str]:
        resolver = GristTableResolver(api, doc_id)
        created_pages: list[str] = []
        added_promoted_widget = False

        for page in plan.pages:
            try:
                view_id = self._create_page(api, doc_id, page.name)
            except Exception as exc:
                logger.error("Failed to create page '%s': %s", page.name, exc)
                continue

            rendered_tables: dict[str, int] = {}

            for section in page.sections:
                if not section.table:
                    continue
                # Resolve semantic table names to actual Grist table names
                table_name = section.table
                # Direct lookup in table_mapping (role → actual name)
                if table_name in classification.table_mapping:
                    table_name = classification.table_mapping[table_name]
                else:
                    # Case-insensitive fallback for variations like "employees" vs "Employees"
                    lower = table_name.lower().strip()
                    for role, actual in classification.table_mapping.items():
                        if role.lower() == lower:
                            table_name = actual
                            break
                try:
                    table_ref = resolver.get_ref(table_name)
                    rendered_tables[table_name] = table_ref
                except KeyError:
                    logger.warning(
                        "Table '%s' not in doc — skipping section '%s'",
                        section.table, section.title,
                    )
                    continue
                try:
                    if section.widget == "chart" and section.chart_type:
                        if section.chart_type == "line" and (not section.x or not section.y):
                            logger.warning(
                                "Skipping line chart '%s' because x or y axis is missing",
                                section.title,
                            )
                            continue
                        self._add_chart_section(
                            api, doc_id, view_id, table_ref,
                            section.chart_type, section.title or "",
                            x_col=section.x,
                            y_col=section.y,
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

            if not added_promoted_widget:
                try:
                    added_promoted_widget = self._maybe_add_promoted_widget(
                        api,
                        doc_id,
                        view_id,
                        page.name,
                        rendered_tables,
                        visual_intents,
                    )
                except Exception as exc:
                    logger.error("Promoted widget failed on page '%s': %s", page.name, exc)

            created_pages.append(page.name)

        created_pages.extend(
            self._materialize_additional_visual_widgets(
                api,
                doc_id,
                resolver,
                visual_intents,
            )
        )

        return created_pages
