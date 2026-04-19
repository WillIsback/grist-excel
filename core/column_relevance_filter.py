# core/column_relevance_filter.py
"""Agent 2.5 — Column Relevance Filter.

Trims DataProfile.stats to intent-relevant columns using two-threshold
hysteresis + table solidarity. Only profile.stats is filtered; structural
fields (columns, sheets, apparent_fk, summary_tables) are preserved.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import requests
from typing import Any

from pydantic import BaseModel

from config import Settings
from core.data_analyzer import DataProfile

logger = logging.getLogger(__name__)


class _ColumnScores(BaseModel):
    scores: dict[str, float]  # "Table.Column" -> 0.0-1.0


class ColumnRelevanceFilter:
    """Filters DataProfile.stats to columns relevant to user_intent."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def filter(self, profile: DataProfile, user_intent: str) -> DataProfile:
        """Return DataProfile with stats trimmed to intent-relevant columns.

        Returns original profile unchanged if user_intent is empty or if
        the filter result would have fewer than RELEVANCE_MIN_COLUMNS columns.
        """
        if not user_intent.strip():
            return profile

        all_keys = list(profile.stats.keys())
        if not all_keys:
            return profile

        scores = self._score_columns(all_keys, user_intent)
        included = self._apply_hysteresis(scores)

        if len(included) < self.settings.RELEVANCE_MIN_COLUMNS:
            logger.warning(
                "ColumnRelevanceFilter: only %d columns passed — falling back to full profile",
                len(included),
            )
            return profile

        trimmed_stats = {k: v for k, v in profile.stats.items() if k in included}
        return dataclasses.replace(profile, stats=trimmed_stats)

    def _score_columns(self, column_keys: list[str], user_intent: str) -> dict[str, float]:
        """Call vLLM to score each column's relevance to user_intent (0.0–1.0)."""
        col_list = "\n".join(f"  - {k}" for k in column_keys)
        prompt = (
            f"Question utilisateur : \"{user_intent}\"\n\n"
            f"Évaluez la pertinence de chaque colonne (0.0=non pertinent, 1.0=très pertinent) "
            f"pour répondre à cette question.\n\n"
            f"Colonnes à évaluer :\n{col_list}\n\n"
            f"Répondez UNIQUEMENT en JSON avec exactement les clés fournies :\n"
            f'{{"scores": {{"Table.Colonne": 0.0, ...}}}}'
        )
        messages = [
            {
                "role": "system",
                "content": "Vous êtes un analyste de pertinence de données. Répondez UNIQUEMENT en JSON valide.",
            },
            {"role": "user", "content": prompt},
        ]
        schema = _ColumnScores.model_json_schema()
        url = f"{self.settings.VLLM_BASE_URL.rstrip('/')}/v1/chat/completions"
        payload = {
            "model": self.settings.VLLM_MODEL,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.1,
            "chat_template_kwargs": {"enable_thinking": False},
            "extra_body": {"guided_json": schema},
        }
        resp = requests.post(url, json=payload, timeout=self.settings.VLLM_TIMEOUT)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"].get("content", "")
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            content = json_match.group(0)
        raw_scores: dict[str, float] = json.loads(content).get("scores", {})
        return {k: float(raw_scores.get(k, 0.5)) for k in column_keys}

    def _apply_hysteresis(self, scores: dict[str, float]) -> set[str]:
        """Two-threshold hysteresis + table solidarity.

        Hard-in  (>= RELEVANCE_UPPER): always included.
        Hard-out (<= RELEVANCE_LOWER): always excluded.
        Soft zone (between): included if same table as any hard-in column,
        then filled by score descending until RELEVANCE_MIN_COLUMNS floor.
        """
        upper = self.settings.RELEVANCE_UPPER
        lower = self.settings.RELEVANCE_LOWER
        min_cols = self.settings.RELEVANCE_MIN_COLUMNS

        hard_in: set[str] = {k for k, s in scores.items() if s >= upper}
        hard_in_tables: set[str] = {k.split(".")[0] for k in hard_in}

        soft_zone: list[tuple[str, float]] = sorted(
            [(k, s) for k, s in scores.items() if lower < s < upper],
            key=lambda x: x[1],
            reverse=True,
        )

        included: set[str] = set(hard_in)

        # Table solidarity pass
        for key, _ in soft_zone:
            table = key.split(".")[0]
            if table in hard_in_tables:
                included.add(key)

        # Floor pass — fill from soft zone by score until minimum reached
        for key, _ in soft_zone:
            if len(included) >= min_cols:
                break
            included.add(key)

        return included
