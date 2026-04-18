"""Agent 2 — Domain Classifier.

Takes a DataProfile and classifies the business domain using vLLM guided_json.
All output values are constrained to the lists provided in the DataProfile.

Outputs: ClassificationResult (archetype, confidence, table_mapping, params)
"""

from __future__ import annotations

import json
import requests
from typing import Any
from pydantic import BaseModel, Field, field_validator

from config import Settings
from core.data_analyzer import DataProfile


ARCHETYPE_CHOICES = [
    "HR",
    "DECISIONNEL",
    "SUPPORT",
    "STUDENT",
    "SI",
    "PROJECT",
    "GENERIC",
]


class ClassificationResult(BaseModel):
    """Output schema for the Domain Classifier agent."""

    archetype: str = Field(
        description="Business domain archetype. Must be one of: " + ", ".join(ARCHETYPE_CHOICES)
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score between 0.0 and 1.0"
    )
    table_mapping: dict[str, str] = Field(
        description="Maps semantic role names to actual sheet/table names from the data. "
                    "Keys are semantic roles (e.g. 'employees', 'absences'). "
                    "Values must be exact sheet names from the input data."
    )
    params: dict[str, str] = Field(
        description="Maps semantic parameter names to actual column names from the data. "
                    "Keys are parameter names (e.g. 'name_col', 'department_col'). "
                    "Values must be exact column names from the input data."
    )

    @field_validator("archetype")
    @classmethod
    def validate_archetype(cls, v: str) -> str:
        if v not in ARCHETYPE_CHOICES:
            raise ValueError(f"archetype must be one of {ARCHETYPE_CHOICES}, got '{v}'")
        return v

    def model_post_init(self, __context: Any) -> None:
        """Automatically downgrade to GENERIC when confidence is too low."""
        self.enforce_low_confidence_generic()

    def enforce_low_confidence_generic(self) -> "ClassificationResult":
        """Force GENERIC archetype when confidence < 0.6."""
        if self.confidence < 0.6:
            self.archetype = "GENERIC"
        return self


class DomainClassifier:
    """Classifies a DataProfile into a business domain archetype."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def classify(self, profile: DataProfile) -> ClassificationResult:
        """Classify the data profile into a business domain.

        Args:
            profile: DataProfile from Agent 1

        Returns:
            ClassificationResult with archetype, confidence, mappings
        """
        prompt = self._build_prompt(profile)
        messages = [
            {
                "role": "system",
                "content": (
                    "Vous êtes un classificateur de domaine métier. "
                    "Analysez le profil de données et identifiez le domaine métier. "
                    "RÉPONDEZ UNIQUEMENT en JSON valide selon le schéma demandé. "
                    "Ne générez jamais de valeurs libres — utilisez uniquement "
                    "les noms de feuilles et colonnes fournis dans les données."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        result = ClassificationResult(**self._call_llm(messages))
        return result.enforce_low_confidence_generic()

    def _build_prompt(self, profile: DataProfile) -> str:
        """Build the classification prompt from the DataProfile."""
        sheets = profile.sheets
        columns = profile.columns
        fk = profile.apparent_fk

        prompt_lines = [
            "Classez ce jeu de données dans un domaine métier.",
            "",
            "Feuilles disponibles :",
        ]
        for sheet in sheets:
            cols = columns.get(sheet, [])
            prompt_lines.append(f"  - {sheet}: {', '.join(cols)}")

        prompt_lines.extend([
            "",
            "Relations détectées :",
        ])
        if fk:
            for relation in fk:
                prompt_lines.append(f"  - {relation['from']} → {relation['to']}")
        else:
            prompt_lines.append("  (aucune)")

        prompt_lines.extend([
            "",
            "Schéma JSON attendu :",
            json.dumps(ClassificationResult.model_json_schema(), ensure_ascii=False, indent=2),
            "",
            "IMPORTANT: Les valeurs de 'table_mapping' doivent être EXACTEMENT les noms de feuilles ci-dessus. "
            "Les valeurs de 'params' doivent être EXACTEMENT les noms de colonnes ci-dessus.",
        ])

        return "\n".join(prompt_lines)

    def _call_llm(
        self, messages: list[dict], schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Call vLLM with guided_json schema.

        Override this method in tests or for alternative LLM backends.

        Args:
            messages: Chat completion messages
            schema: Optional JSON schema for guided generation.
                    If not provided, uses ClassificationResult schema.

        Returns:
            Parsed JSON response as a dict
        """
        effective_schema = schema or ClassificationResult.model_json_schema()
        url = f"{self.settings.VLLM_BASE_URL}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3,
            "extra_body": {
                "guided_json": effective_schema,
            },
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
