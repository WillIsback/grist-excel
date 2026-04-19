"""Agent 3.6 — Narrative Generator.

Generates a rich analytical summary in Markdown from the full pipeline context:
DataProfile stats, ClassificationResult, InsightReport, and FeaturePlan.
"""

from __future__ import annotations

import json
import logging
import re
import requests
from typing import TYPE_CHECKING, Any

from config import Settings
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport

if TYPE_CHECKING:
    from core.feature_engineer import FeaturePlan

logger = logging.getLogger(__name__)


class NarrativeGenerator:
    """Generates an executive-style analytical narrative using LLM."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def generate(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None" = None,
        user_intent: str | None = None,
    ) -> str:
        """Generate a rich Markdown analytical summary.

        Returns:
            Markdown string starting with a heading, ready for the Grist
            Markdown widget.  Falls back to a minimal bullet list on LLM failure.
        """
        prompt = self._build_prompt(profile, classification, insights, feature_plan, user_intent)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un analyste de données senior. "
                    "Rédigez un résumé analytique exécutif en Markdown à partir des données fournies. "
                    "Le résumé doit inclure : une synthèse des indicateurs clés, les risques identifiés, "
                    "les opportunités d'action, et les points de vigilance sur la qualité des données. "
                    "Soyez factuel, précis, et utilisez les chiffres fournis. "
                    "Structurez avec des titres de niveau 2 (##). "
                    "Répondez UNIQUEMENT en Markdown, sans balises de code, sans JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        try:
            return self._call_llm(messages)
        except Exception as exc:
            logger.warning("NarrativeGenerator LLM failed: %s — falling back to bullets", exc)
            return self._fallback_narrative(insights)

    def _build_prompt(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
        feature_plan: "FeaturePlan | None",
        user_intent: str | None,
    ) -> str:
        lines = [
            f"Domaine métier : {classification.archetype}",
            "",
            "Tables et colonnes :",
        ]
        for role, table_name in classification.table_mapping.items():
            cols = profile.columns.get(table_name, [])
            lines.append(f"  {role} ({table_name}) : {', '.join(cols)}")

        lines.extend(["", "Statistiques clés :"])
        for key, stats in profile.stats.items():
            parts = []
            if "non_null" in stats:
                parts.append(f"n={stats['non_null']}")
            if "unique" in stats:
                parts.append(f"unique={stats['unique']}")
            if "min" in stats and "max" in stats and "avg" in stats:
                parts.append(f"min={stats['min']:.0f} max={stats['max']:.0f} avg={stats['avg']:.0f}")
            if "top" in stats:
                top_vals = ", ".join(str(v) for v in stats["top"][:5])
                parts.append(f"top=[{top_vals}]")
            if parts:
                lines.append(f"  {key}: {' | '.join(parts)}")

        lines.extend(["", f"Insights extraits ({len(insights.insights)}) :"])
        for ins in sorted(insights.insights, key=lambda i: i.priority):
            lines.append(f"  [{ins.type}] {ins.table}.{ins.col} (priorité {ins.priority}): {ins.finding}")

        if feature_plan and feature_plan.features:
            lines.extend(["", "Colonnes dérivées créées :"])
            for f in feature_plan.features:
                lines.append(f"  {f.col_id} ({f.type}) : {f.label}")

        if profile.summary_tables:
            lines.extend(["", "Tables de synthèse croisée disponibles :"])
            for t in profile.summary_tables:
                lines.append(f"  {t['group_by']} × {t['metric']} ({t['source_table']})")

        if user_intent and user_intent.strip():
            lines.extend(["", f"Question de l'utilisateur : {user_intent}"])

        lines.extend([
            "",
            "Rédigez un résumé analytique exécutif en Markdown couvrant :",
            "  1. ## Vue d'ensemble — chiffres clés du dataset",
            "  2. ## Indicateurs de risque — signaux d'alerte identifiés",
            "  3. ## Points d'action — recommandations concrètes et prioritaires",
            "  4. ## Qualité des données — valeurs manquantes, anomalies, limites",
        ])
        if user_intent and user_intent.strip():
            lines.append(f"  5. ## Réponse à la question — répondez directement à : {user_intent}")

        return "\n".join(lines)

    def _call_llm(self, messages: list[dict]) -> str:
        url = f"{self.settings.VLLM_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.4,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning") or ""
        return content.strip()

    def _fallback_narrative(self, insights: InsightReport) -> str:
        lines = ["# Résumé analytique", ""]
        for ins in sorted(insights.insights, key=lambda i: i.priority):
            lines.append(f"- **{ins.table} / {ins.col}** : {ins.finding}")
        return "\n".join(lines)
