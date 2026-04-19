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
    from core.visual_intents import VisualIntentPlan

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
        retry_context: dict | None = None,
        raw_cols: dict | None = None,
        stats: dict | None = None,
        summary_tables: list[dict[str, Any]] | None = None,
        visual_intents: "VisualIntentPlan | None" = None,
    ) -> DashboardPlan:
        """Compose a dashboard plan."""
        prompt = self._build_prompt(classification, insights, feature_plan, retry_context,
                                    raw_cols=raw_cols, stats=stats,
                                    summary_tables=summary_tables,
                                    visual_intents=visual_intents)
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
                    if section.get("chart_type") == "line":
                        if not section.get("x") or not section.get("y"):
                            continue
                valid_sections.append(section)
            page["sections"] = valid_sections
        raw_data["pages"] = pages_data
        plan = DashboardPlan(**raw_data)
        return self._append_summary_sections(plan, summary_tables, visual_intents)

    def _append_summary_sections(
        self,
        plan: DashboardPlan,
        summary_tables: list[dict[str, Any]] | None,
        visual_intents: "VisualIntentPlan | None" = None,
    ) -> DashboardPlan:
        """Append deterministic grid widgets for precomputed summary tables."""
        intent_sections = []
        promoted_source_table = None
        if visual_intents is not None:
            promoted_intent = visual_intents.get_promoted_intent()
            if promoted_intent and promoted_intent.kind == "cross_tab":
                promoted_source_table = promoted_intent.source_table
            intent_sections = [
                PageSection(
                    widget="table",
                    table=intent.source_table,
                    title=intent.title,
                )
                for intent in visual_intents.intents
                if intent.kind == "cross_tab"
            ]
            if promoted_source_table:
                intent_sections.sort(
                    key=lambda section: 0 if section.table == promoted_source_table else 1
                )

        if intent_sections:
            pages = list(plan.pages)
            pages.append(Page(name="Syntheses croisees", sections=intent_sections))
            return DashboardPlan(pages=pages)

        if not summary_tables:
            return plan

        sections = [
            PageSection(
                widget="table",
                table=table["name"],
                title=f"Croisement {table['group_by']} x {table['metric']}",
            )
            for table in summary_tables
        ]
        if not sections:
            return plan

        pages = list(plan.pages)
        pages.append(Page(name="Syntheses croisees", sections=sections))
        return DashboardPlan(pages=pages)

    def _build_prompt(
        self,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
        retry_context: dict | None = None,
        raw_cols: dict | None = None,
        stats: dict | None = None,
        summary_tables: list[dict[str, Any]] | None = None,
        visual_intents: "VisualIntentPlan | None" = None,
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

        if raw_cols:
            prompt_lines.extend(["", "Colonnes disponibles par table (N=numérique, T=texte/ID) :"])
            for table_id, cols in raw_cols.items():
                typed_cols = []
                for col in cols:
                    key = f"{table_id}.{col}"
                    col_stats = (stats or {}).get(key, {})
                    is_numeric = "min" in col_stats and "avg" in col_stats
                    typed_cols.append(f"{col}({'N' if is_numeric else 'T'})")
                prompt_lines.append(f"  {table_id}: {', '.join(typed_cols)}")

        prompt_lines.extend([
            "",
            "Règles OBLIGATOIRES pour les charts :",
            "  - x et y DOIVENT être deux colonnes DIFFÉRENTES",
            "  - x : colonne catégorielle (T) — ex: Département, Type, Manager, Région",
            "  - y : colonne numérique (N) — ex: Salaire_Brute, Durée_Jours, Ancienneté_Jours",
            "  - Pour agg=count, y = colonne ID de la table (ex: ID_Absence, ID_Employe)",
            "  - Distribution de catégories (x=Text avec ≥3 valeurs) → pie ou bar",
            "  - Colonne Toggle/booléen (True/False) → bar UNIQUEMENT (pas pie)",
            "  - Tendance temporelle (x=date) → line",
            "  - Comparaison de moyennes → bar",
            "  - N'écrivez JAMAIS 'ID' seul — utilisez le nom exact de la colonne ci-dessus",
            "  - N'utilisez PAS de colonnes dérivées (Toggle) comme x dans un pie chart",
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

        if summary_tables:
            prompt_lines.extend([
                "",
                "Tables de synthèse croisée précalculées disponibles pour widgets table :",
            ])
            for table in summary_tables:
                prompt_lines.append(
                    f"  {table['name']} : {table['group_by']} x {table['metric']} ({table['source_table']})"
                )

        if visual_intents and visual_intents.intents:
            prompt_lines.extend([
                "",
                "Intentions visuelles déterministes dérivées de l'analyse :",
            ])
            for intent in visual_intents.intents:
                prompt_lines.append(
                    f"  [{intent.kind}] {intent.title} -> supported={intent.supported_widgets}, "
                    f"premium={intent.premium_widgets}, preferred={intent.preferred_widget}, "
                    f"presentation={intent.presentation}, source={intent.source_table}"
                )
            promoted_intent = visual_intents.get_promoted_intent()
            promoted_widget = visual_intents.get_promoted_widget()
            if promoted_intent and promoted_widget:
                prompt_lines.extend([
                    "",
                    "Intention premium à privilégier si possible :",
                    (
                        f"  {promoted_intent.title} -> widget premium={promoted_widget}, "
                        f"preferred={promoted_intent.preferred_widget}, source={promoted_intent.source_table}"
                    ),
                ])

        if retry_context:
            prompt_lines.extend([
                "",
                "⚠ RETRY — sections précédentes rejetées (colonnes inexistantes) :",
            ])
            for line in retry_context.get("dropped_sections", []):
                prompt_lines.append(line)
            prompt_lines.extend([
                "",
                "Colonnes disponibles (utilisez UNIQUEMENT celles-ci) :",
            ])
            for table_id, cols in retry_context.get("available_columns", {}).items():
                prompt_lines.append(f"  {table_id}: {', '.join(cols)}")

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
