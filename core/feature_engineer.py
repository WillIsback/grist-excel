"""Agent 3.5 — Feature Engineer.

Plans and applies Grist formula columns derived from LLM insights.
Two-phase:
  1. plan() — LLM generates FeaturePlan (formula columns to create)
  2. apply() — writes formula cols to live Grist document via PATCH API
"""

from __future__ import annotations

import json
import logging
import re
import requests
from typing import Any

from pydantic import BaseModel, Field

from config import Settings
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport

logger = logging.getLogger(__name__)


class FormulaColumn(BaseModel):
    """A derived Grist column defined by a Python formula."""

    table: str = Field(description="Semantic table role (key in table_mapping, e.g. 'employees')")
    col_id: str = Field(description="Grist column ID — ASCII only, no spaces")
    label: str = Field(description="Human-readable label (French)")
    type: str = Field(description="Grist type: Toggle, Int, Numeric, Text")
    formula: str = Field(description="Grist Python formula using $ColName and Table.lookupRecords() syntax")


class FeaturePlan(BaseModel):
    """Plan of derived columns to create in the Grist document."""

    features: list[FormulaColumn] = Field(
        default_factory=list,
        max_length=6,
        description="Derived columns to create (0–6)",
    )


GRIST_FORMULA_EXAMPLES = """
# Count related records
len(Absences.lookupRecords(ID_Employe=$ID_Employe))

# Boolean existence check (returns True/False)
bool(Evaluations.lookupOne(ID_Employe=$ID_Employe).ID_Employe)

# Numeric bucketing
"Haut" if $Salaire_Brute > 70000 else ("Moyen" if $Salaire_Brute > 45000 else "Bas")

# Average from related table (safe division)
(sum(Evaluations.lookupRecords(ID_Employe=$ID_Employe).Note) /
 max(len(Evaluations.lookupRecords(ID_Employe=$ID_Employe)), 1))

# Days since a date column
(TODAY() - $Date_Embauche).days if $Date_Embauche else 0

# Boolean null check
not bool($Manager)
"""


class FeatureEngineer:
    """Plans and applies derived Grist formula columns."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def plan(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
    ) -> FeaturePlan:
        prompt = self._build_prompt(profile, classification, insights)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un ingénieur de données Grist. "
                    "Générez des colonnes de formule Grist Python pour rendre les insights chartables. "
                    "Utilisez UNIQUEMENT les noms de colonnes fournis. "
                    "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        data = self._call_llm(messages)
        return FeaturePlan(**data)

    def _build_prompt(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
    ) -> str:
        lines = [
            f"Archetype : {classification.archetype}",
            "",
            "Tables et colonnes disponibles :",
        ]
        for role, table_name in classification.table_mapping.items():
            cols = profile.columns.get(table_name, [])
            lines.append(f"  {role} ({table_name}): {', '.join(cols)}")

        lines.extend([
            "",
            "Insights à rendre chartables :",
        ])
        for ins in insights.insights:
            lines.append(f"  [{ins.type}] {ins.table}.{ins.col}: {ins.finding}")

        lines.extend([
            "",
            "Exemples de formules Grist Python valides :",
            GRIST_FORMULA_EXAMPLES,
            "",
            "Règles :",
            "  - col_id: ASCII uniquement, pas d'espaces, pas d'accents",
            "  - table: clé sémantique du mapping (ex: 'employees', 'absences')",
            "  - Référencez des tables exactement comme dans le mapping",
            "  - 0 features si aucun insight ne nécessite de colonne dérivée",
            "",
            "Schéma JSON attendu :",
            json.dumps(FeaturePlan.model_json_schema(), ensure_ascii=False, indent=2),
        ])
        return "\n".join(lines)

    def _call_llm(
        self,
        messages: list[dict],
        schema: dict[str, Any] | None = None,
        *,
        _retry: bool = False,
    ) -> dict[str, Any]:
        effective_schema = schema or FeaturePlan.model_json_schema()
        url = f"{self.settings.VLLM_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.2,
            "chat_template_kwargs": {"enable_thinking": False},
            "extra_body": {"guided_json": effective_schema},
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or message.get("reasoning")
        if content is None:
            raise ValueError("Empty response from LLM")
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            content = json_match.group(0)
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            if _retry:
                raise ValueError(f"LLM returned invalid JSON after retry: {content!r}") from exc
            logger.warning("JSON decode failed, retrying with stricter prompt.")
            stricter = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "Votre réponse n'est pas du JSON valide. "
                    "Répondez UNIQUEMENT avec du JSON valide sans texte supplémentaire."
                )},
            ]
            return self._call_llm(stricter, schema=effective_schema, _retry=True)
