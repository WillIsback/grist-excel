"""Agent 4 — Dashboard Composer.

Takes a ClassificationResult + InsightReport and composes a DashboardPlan
using vLLM guided_json. Includes a self-reflection pass to validate
that every widget is justified by an insight.
"""

from __future__ import annotations

import json
import logging
import re
import requests
from typing import TYPE_CHECKING, Any
from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from core.feature_engineer import FeaturePlan

logger = logging.getLogger(__name__)

from config import Settings
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport


WIDGET_TYPES = ["chart", "table", "card_list", "card", "form"]
CHART_TYPES = ["bar", "line", "pie", "area"]


class PageSection(BaseModel):
    """A single widget section within a dashboard page."""

    widget: str = Field(description=f"Widget type. One of: {', '.join(WIDGET_TYPES)}")
    title: str = Field(description="Human-readable title for the widget")

    # Chart-specific fields (optional, only for widget="chart")
    chart_type: str | None = Field(default=None, description=f"Chart type. One of: {', '.join(CHART_TYPES)}")
    table: str | None = Field(default=None, description="Source table/sheet name")
    x: str | None = Field(default=None, description="X-axis column name")
    y: str | None = Field(default=None, description="Y-axis column name")
    agg: str | None = Field(default=None, description="Aggregation function: count, sum, avg, max, min")

    @field_validator("widget")
    @classmethod
    def validate_widget(cls, v: str) -> str:
        if v not in WIDGET_TYPES:
            raise ValueError(f"widget must be one of {WIDGET_TYPES}, got '{v}'")
        return v

    @field_validator("chart_type")
    @classmethod
    def validate_chart_type(cls, v: str | None) -> str | None:
        if v is not None and v not in CHART_TYPES:
            raise ValueError(f"chart_type must be one of {CHART_TYPES}, got '{v}'")
        return v

    @model_validator(mode="after")
    def validate_chart_fields(self):
        if self.widget == "chart" and not self.chart_type:
            raise ValueError("chart widgets require chart_type field")
        return self


class Page(BaseModel):
    """A page in the dashboard containing multiple sections."""

    name: str = Field(description="Page name/title")
    sections: list[PageSection] = Field(description="List of widget sections on this page")


class DashboardPlan(BaseModel):
    """Complete dashboard plan with pages and sections."""

    pages: list[Page] = Field(description="List of dashboard pages")

    def self_reflect(self, insights: InsightReport) -> "DashboardPlan":
        """Validate that every widget is justified by an insight.

        Removes widgets whose titles don't match any insight finding.
        Returns a cleaned plan.
        """
        findings_lower = {ins.finding.lower() for ins in insights.insights}

        cleaned_pages = []
        for page in self.pages:
            kept_sections = []
            for section in page.sections:
                if section.widget == "chart" and section.title:
                    title_lower = section.title.lower()
                    matched = any(f in title_lower or title_lower in f for f in findings_lower)
                    if not matched:
                        continue
                kept_sections.append(section)
            if kept_sections:
                cleaned_pages.append(Page(name=page.name, sections=kept_sections))

        return DashboardPlan(pages=cleaned_pages)


class DashboardComposer:
    """Composes a dashboard plan from classification and insights."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def compose(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
    ) -> DashboardPlan:
        """Compose a dashboard plan.

        Args:
            classification: ClassificationResult from Agent 2
            insights: InsightReport from Agent 3
            feature_plan: FeaturePlan from Agent 3.5 (optional)

        Returns:
            DashboardPlan with pages and sections
        """
        prompt = self._build_prompt(classification, insights, feature_plan)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un architecte de dashboards Grist. "
                    "Composez un plan de dashboard basé sur les insights métier fournis. "
                    "Mappez chaque insight à un widget de chart. "
                    "Ajoutez aussi une page formulaire pour la table principale. "
                    "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        raw_data = self._call_llm(messages)
        # Filter out invalid chart sections before Pydantic validation
        pages_data = raw_data.get("pages", [])
        for page in pages_data:
            valid_sections = []
            for section in page.get("sections", []):
                if section.get("widget") == "chart":
                    if not section.get("chart_type"):
                        continue
                valid_sections.append(section)
            page["sections"] = valid_sections
        raw_data["pages"] = pages_data
        return DashboardPlan(**raw_data)

    def _build_prompt(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
    ) -> str:
        """Build the composition prompt."""
        archetype = classification.archetype
        mapping = classification.table_mapping

        prompt_lines = [
            f"Archetype : {archetype}",
            "",
            "Mapping tables :",
        ]
        for role, table in mapping.items():
            prompt_lines.append(f"  {role} → {table}")

        prompt_lines.extend([
            "",
            "Insights:",
        ])
        for ins in insights.insights:
            prompt_lines.append(f"  [{ins.type}] {ins.table}.{ins.col}: {ins.finding} (priority {ins.priority})")

        if feature_plan and feature_plan.features:
            prompt_lines.extend([
                "",
                "Colonnes dérivées disponibles (créées par FeatureEngineer) :",
            ])
            for f in feature_plan.features:
                table_id = classification.table_mapping.get(f.table, f.table)
                prompt_lines.append(f"  {table_id}.{f.col_id} ({f.type}) : {f.label}")

        prompt_lines.extend([
            "",
            "Pages à créer :",
            "  1. Dashboard principal avec des charts basés sur les insights",
            "  2. Page liste/cards pour la table principale",
            "  3. Page formulaire pour la table principale",
            "",
            "Schéma JSON attendu :",
            json.dumps(DashboardPlan.model_json_schema(), ensure_ascii=False, indent=2),
        ])

        return "\n".join(prompt_lines)

    def _call_llm(
        self,
        messages: list[dict],
        schema: dict[str, Any] | None = None,
        *,
        _retry: bool = False,
    ) -> dict[str, Any]:
        """Call vLLM with guided_json schema.

        On JSON decode failure, retries once with a stricter prompt appended.

        Raises:
            ValueError: If LLM returns invalid JSON after retry.
        """
        effective_schema = schema or DashboardPlan.model_json_schema()
        url = f"{self.settings.VLLM_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False},
            "extra_body": {
                "guided_json": effective_schema,
            },
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning")
        if content is None:
            raise ValueError("Empty response from LLM")
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            content = json_match.group(0)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            if _retry:
                raise ValueError(
                    f"LLM returned invalid JSON after retry: {content!r}"
                ) from exc
            logger.warning("JSON decode failed, retrying with stricter prompt.")
            stricter_messages = messages + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Votre réponse n'est pas du JSON valide. "
                        "Répondez UNIQUEMENT avec du JSON valide correspondant au schéma fourni, "
                        "sans texte supplémentaire ni balises markdown."
                    ),
                },
            ]
            return self._call_llm(stricter_messages, schema=effective_schema, _retry=True)
