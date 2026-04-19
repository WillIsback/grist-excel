"""Agent 3 — Insight Extractor.

Takes a DataProfile + ClassificationResult and extracts business insights
using vLLM guided_json.

Insights cover: distribution, trend, outlier, relation, kpi
Max 5 insights, sorted by priority.
"""

from __future__ import annotations

import json
import logging
import re
import requests
from typing import Any
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

from config import Settings
from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult


VALID_INSIGHT_TYPES = [
    "distribution",
    "trend",
    "outlier",
    "relation",
    "kpi",
]


class InsightEntry(BaseModel):
    """Single insight extracted from data analysis."""

    type: str = Field(
        description=f"Type of insight. Must be one of: {', '.join(VALID_INSIGHT_TYPES)}"
    )
    table: str = Field(
        description="Exact table/sheet name from the data"
    )
    col: str = Field(
        description="Exact column name from the data"
    )
    finding: str = Field(
        description="Human-readable finding summary in French"
    )
    priority: int = Field(
        ge=1, le=5,
        description="Priority rank 1-5 (1 = most important)"
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in VALID_INSIGHT_TYPES:
            raise ValueError(f"type must be one of {VALID_INSIGHT_TYPES}, got '{v}'")
        return v


class InsightReport(BaseModel):
    """Report containing up to 5 business insights."""

    insights: list[InsightEntry] = Field(
        max_length=5,
        description="List of insights, max 5, sorted by priority"
    )


class InsightExtractor:
    """Extracts business insights from data using LLM analysis."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def extract(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        user_intent: str | None = None,
    ) -> InsightReport:
        """Extract business insights from the data.

        Args:
            profile: DataProfile from Agent 1
            classification: ClassificationResult from Agent 2
            user_intent: Optional user question; when provided, focuses extraction
                exclusively on insights relevant to it.

        Returns:
            InsightReport with up to 5 insights
        """
        prompt = self._build_prompt(profile, classification)
        system_content = (
            "Vous êtes un analyste de données métier. "
            "Extrayez maximum 5 insights pertinents du profil de données. "
            "Pour chaque insight, indiquez le type, la table, la colonne concernée, "
            "et un résumé du résultat en français. "
            "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé."
        )
        if user_intent and user_intent.strip():
            system_content += (
                f"\n\nFOCUS EXCLUSIF sur la question de l'utilisateur : {user_intent}"
                "\nIgnorez les insights non liés à cette question."
            )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ]
        return InsightReport(**self._call_llm(messages))

    def _build_prompt(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
    ) -> str:
        """Build the insight extraction prompt."""
        archetype = classification.archetype
        mapping = classification.table_mapping

        prompt_lines = [
            f"Domaine métier identifié : {archetype}",
            "",
            "Mapping des tables :",
        ]
        for role, table in mapping.items():
            prompt_lines.append(f"  {role} → {table}")

        prompt_lines.extend([
            "",
            "Profil de données :",
            profile.to_json(),
            "",
            "Analysez ces données sous les angles suivants :",
            "  - distribution : répartition des valeurs par catégorie",
            "  - trend : évolutions temporelles",
            "  - outlier : valeurs anomales",
            "  - relation : corrélations entre colonnes/tableaux",
            "  - kpi : indicateurs clés de performance",
            "",
            "Schéma JSON attendu :",
            json.dumps(InsightReport.model_json_schema(), ensure_ascii=False, indent=2),
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

        Args:
            messages: Chat completion messages
            schema: Optional JSON schema for guided generation.
                    If not provided, uses InsightReport schema.

        Returns:
            Parsed JSON response as a dict

        Raises:
            ValueError: If LLM returns invalid JSON after retry.
        """
        effective_schema = schema or InsightReport.model_json_schema()
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
