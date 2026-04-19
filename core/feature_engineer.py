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
from core.debug_utils import debug_print
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
# IMPORTANT: utiliser le NOM EXACT de la table tel que fourni dans le mapping ci-dessus
# (avec accents si présents — ex: "Évaluations" pas "Evaluations")

# Compter des enregistrements liés (remplacer TABLE et COL_FK par les vrais noms)
len(TABLE.lookupRecords(COL_FK=$COL_PK))

# Vérification d'existence booléenne
bool(TABLE.lookupOne(COL_FK=$COL_PK).COL_FK)

# Bucketing numérique
"Haut" if $ColNum > 70000 else ("Moyen" if $ColNum > 45000 else "Bas")

# Moyenne d'une table liée (division sécurisée)
(sum(TABLE.lookupRecords(COL_FK=$COL_PK).ColVal) /
 max(len(TABLE.lookupRecords(COL_FK=$COL_PK)), 1))

# Jours depuis une date
(TODAY() - $DateCol).days if $DateCol else 0

# Null check booléen
not bool($ColNullable)
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

        lines.extend(["", "Noms EXACTS des tables Grist à utiliser dans les formules :"])
        for role, table_name in classification.table_mapping.items():
            lines.append(f"  {role} → '{table_name}' (accents inclus)")

        lines.extend([
            "",
            "Exemples de formules Grist Python valides :",
            GRIST_FORMULA_EXAMPLES,
            "",
            "Règles :",
            "  - col_id: ASCII uniquement, pas d'espaces, pas d'accents",
            "  - table: clé sémantique du mapping (ex: 'employees', 'absences')",
            "  - Dans les formules Python lookupRecords, utiliser le NOM EXACT ci-dessus",
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

    def apply(
        self,
        api: Any,
        doc_id: str,
        plan: FeaturePlan,
        table_mapping: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        """Write formula columns from FeaturePlan to a live Grist document."""
        applied: list[str] = []
        failed: list[str] = []

        for feature in plan.features:
            table_id = table_mapping.get(feature.table, feature.table)
            columns_payload = [{
                "id": feature.col_id,
                "fields": {
                    "type": feature.type,
                    "label": feature.label,
                    "formula": feature.formula,
                    "isFormula": True,
                },
            }]
            request_debug = {
                "doc_id": doc_id,
                "semantic_table": feature.table,
                "table_id": table_id,
                "method": "POST",
                "url": None,
                "payload": {"columns": columns_payload},
            }
            if hasattr(api, "_doc_url"):
                try:
                    request_debug["url"] = api._doc_url(doc_id, f"tables/{table_id}/columns")
                except Exception:
                    request_debug["url"] = None
            debug_print("FeatureEngineer.patch_columns", request_debug, self.settings.DEBUG)

            try:
                api.add_columns(doc_id, table_id, columns_payload)
                api.get_records(doc_id, table_id)
                applied.append(feature.col_id)
                logger.info("Feature column applied: %s.%s", table_id, feature.col_id)
            except Exception as exc:
                debug_print(
                    "FeatureEngineer.patch_columns.error",
                    {**request_debug, "error": str(exc)},
                    self.settings.DEBUG,
                )
                logger.warning("Feature column failed: %s.%s — %s", table_id, feature.col_id, exc)
                failed.append(feature.col_id)

        return applied, failed
