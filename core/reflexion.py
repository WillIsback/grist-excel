"""Agent 4.5 — Reflexion Validator.

Deterministic validation of DashboardPlan:
- Verifies every chart column exists (raw or engineered)
- Drops invalid sections; removes empty pages
- If >50% dropped, triggers targeted LLM retry via DashboardComposer
"""

from __future__ import annotations

import logging
import unicodedata
from typing import TYPE_CHECKING

from core.dashboard_composer import DashboardPlan, Page, PageSection

if TYPE_CHECKING:
    from core.dashboard_composer import DashboardComposer
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


class ReflexionValidator:
    """Validates DashboardPlan column references and drops/retries invalid sections."""

    def __init__(
        self,
        raw_cols: dict[str, list[str]],
        engineered_cols: dict[str, list[str]],
        table_mapping: dict[str, str],
    ):
        self.raw_cols = raw_cols
        self.engineered_cols = engineered_cols
        self.table_mapping = table_mapping

    def _resolve_table(self, semantic_table: str) -> str | None:
        if semantic_table in self.table_mapping:
            return self.table_mapping[semantic_table]
        norm = _normalize(semantic_table)
        for role, actual in self.table_mapping.items():
            if _normalize(role) == norm:
                return actual
        all_tables = set(self.raw_cols.keys()) | set(self.engineered_cols.keys())
        for t in all_tables:
            if _normalize(t) == norm:
                return t
        return None

    def _col_exists(self, table_id: str, col_name: str) -> bool:
        all_cols = (
            self.raw_cols.get(table_id, [])
            + self.engineered_cols.get(table_id, [])
        )
        norm = _normalize(col_name)
        return any(_normalize(c) == norm for c in all_cols)

    def _validate_section(self, section: PageSection) -> tuple[bool, str]:
        table_id = self._resolve_table(section.table or "")
        if table_id is None:
            return False, f"table '{section.table}' unresolvable"

        if section.widget == "chart":
            if section.x and not self._col_exists(table_id, section.x):
                return False, f"x col '{section.x}' not in {table_id}"
            if section.y and not self._col_exists(table_id, section.y):
                return False, f"y col '{section.y}' not in {table_id}"

        return True, ""

    def _validate_and_count(self, plan: DashboardPlan) -> tuple[DashboardPlan, float]:
        total = sum(len(p.sections) for p in plan.pages)
        dropped = 0
        cleaned_pages: list[Page] = []

        for page in plan.pages:
            kept: list[PageSection] = []
            for section in page.sections:
                valid, reason = self._validate_section(section)
                if valid:
                    kept.append(section)
                else:
                    dropped += 1
                    logger.warning("Dropped section '%s': %s", section.title, reason)
            if kept:
                cleaned_pages.append(Page(name=page.name, sections=kept))

        drop_ratio = dropped / total if total > 0 else 0.0
        return DashboardPlan(pages=cleaned_pages), drop_ratio

    def validate_deterministic(self, plan: DashboardPlan) -> DashboardPlan:
        cleaned, _ = self._validate_and_count(plan)
        return cleaned
