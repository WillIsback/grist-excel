"""Deterministic visual intent resolver.

Translates existing pipeline outputs into generic visualization intents.
This layer is intentionally rule-based and lightweight: it reuses the business
logic already extracted by the pipeline instead of re-inferring it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.data_analyzer import DataProfile
from core.domain_classifier import ClassificationResult
from core.insight_extractor import InsightReport


VisualWidget = Literal[
    "table",
    "chart",
    "card_list",
    "form",
    "markdown",
    "advanced_chart",
    "map",
    "jupyterlite",
]


VisualIntentKind = Literal[
    "trend",
    "cross_tab",
    "geo",
    "narrative",
    "entity_detail",
]

VisualPresentation = Literal[
    "hero_chart",
    "secondary_chart",
    "summary_page",
    "geo_page",
    "detail_page",
    "narrative_block",
]


class VisualIntent(BaseModel):
    """A generic, deterministic visualization intent derived from analysis."""

    kind: VisualIntentKind
    source_table: str
    source_columns: list[str] = Field(default_factory=list)
    insight_refs: list[int] = Field(default_factory=list)
    priority: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    presentation: VisualPresentation
    supported_widgets: list[VisualWidget] = Field(default_factory=list)
    premium_widgets: list[VisualWidget] = Field(default_factory=list)
    preferred_widget: VisualWidget | None = None
    title: str
    narrative: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualIntentPlan(BaseModel):
    """Collection of visualization intents for one analyzed workbook."""

    intents: list[VisualIntent] = Field(default_factory=list)
    promoted_intent_index: int | None = None
    promoted_widget: VisualWidget | None = None

    def get_promoted_intent(self) -> VisualIntent | None:
        """Return the promoted premium intent, if one was selected."""
        if self.promoted_intent_index is None:
            premium_candidates = [intent for intent in self.intents if intent.premium_widgets]
            if not premium_candidates:
                return None
            return max(
                premium_candidates,
                key=lambda intent: (intent.priority, intent.confidence),
            )
        if 0 <= self.promoted_intent_index < len(self.intents):
            return self.intents[self.promoted_intent_index]
        return None

    def get_promoted_widget(self) -> VisualWidget | None:
        """Return the promoted premium widget, with fallback inference."""
        if self.promoted_widget is not None:
            return self.promoted_widget
        promoted_intent = self.get_promoted_intent()
        if promoted_intent and promoted_intent.premium_widgets:
            return promoted_intent.premium_widgets[0]
        return None


class VisualIntentResolver:
    """Build visual intents from existing pipeline artifacts."""

    def resolve(
        self,
        profile: DataProfile,
        classification: ClassificationResult,
        insights: InsightReport,
        narrative: str | None = None,
    ) -> VisualIntentPlan:
        intents: list[VisualIntent] = []
        intents.extend(self._build_cross_tab_intents(profile, insights))
        intents.extend(self._build_trend_intents(insights, profile))
        intents.extend(self._build_geo_intents(profile))
        intents.extend(self._build_narrative_intents(insights, narrative=narrative))
        intents.extend(self._build_entity_detail_intents(classification))
        promoted_index, promoted_widget = self._select_promoted_premium_intent(intents)
        return VisualIntentPlan(
            intents=intents,
            promoted_intent_index=promoted_index,
            promoted_widget=promoted_widget,
        )

    def _select_promoted_premium_intent(
        self,
        intents: list[VisualIntent],
    ) -> tuple[int | None, VisualWidget | None]:
        """Choose a single premium candidate to prioritize downstream."""
        ranked: list[tuple[float, int, VisualWidget]] = []
        kind_bonus = {
            "trend": 0.08,
            "cross_tab": 0.06,
            "geo": 0.05,
            "narrative": 0.04,
            "entity_detail": 0.02,
        }
        presentation_bonus = {
            "hero_chart": 0.10,
            "secondary_chart": 0.05,
            "summary_page": 0.04,
            "geo_page": 0.04,
            "narrative_block": 0.03,
            "detail_page": 0.01,
        }

        for idx, intent in enumerate(intents):
            if not intent.premium_widgets:
                continue
            score = (intent.priority * 0.7) + (intent.confidence * 0.3)
            score += kind_bonus.get(intent.kind, 0.0)
            score += presentation_bonus.get(intent.presentation, 0.0)
            ranked.append((score, idx, intent.premium_widgets[0]))

        if not ranked:
            return None, None

        ranked.sort(reverse=True)
        _, idx, widget = ranked[0]
        return idx, widget

    def _build_cross_tab_intents(
        self,
        profile: DataProfile,
        insights: InsightReport,
    ) -> list[VisualIntent]:
        intents: list[VisualIntent] = []
        for table in profile.summary_tables:
            matching_refs = []
            for idx, insight in enumerate(insights.insights):
                if insight.table != table["source_table"]:
                    continue
                if insight.col in {table["group_by"], table["metric"]}:
                    matching_refs.append(idx)

            base_priority = 0.55
            if matching_refs:
                best = min(insights.insights[idx].priority for idx in matching_refs)
                base_priority = max(base_priority, 1.0 - ((best - 1) * 0.12))

            intents.append(
                VisualIntent(
                    kind="cross_tab",
                    source_table=table["name"],
                    source_columns=[table["group_by"], table["metric"]],
                    insight_refs=matching_refs,
                    priority=min(base_priority, 0.95),
                    confidence=0.9 if matching_refs else 0.72,
                    presentation="summary_page",
                    supported_widgets=["table"],
                    premium_widgets=["advanced_chart"],
                    preferred_widget="table",
                    title=f"Croisement {table['group_by']} x {table['metric']}",
                    narrative=(
                        f"Synthèse croisée dérivée de {table['source_table']} pour comparer "
                        f"{table['group_by']} et {table['metric']}."
                    ),
                    metadata={
                        "group_by": table["group_by"],
                        "metric": table["metric"],
                        "source_table": table["source_table"],
                    },
                )
            )
        return intents

    def _build_geo_intents(self, profile: DataProfile) -> list[VisualIntent]:
        intents: list[VisualIntent] = []
        for table_name, columns in profile.columns.items():
            lat_col, lon_col = self._find_coordinate_columns(table_name, columns, profile)
            if not lat_col or not lon_col:
                continue

            name_col = self._find_label_column(table_name, columns, profile, exclude={lat_col, lon_col})
            if not name_col:
                continue

            columns_mapping = {
                "Name": name_col,
                "Longitude": lon_col,
                "Latitude": lat_col,
            }
            optional_columns = {
                "Geocode": self._find_column_by_keywords(columns, ["geocode", "geocoder"]),
                "Address": self._find_column_by_keywords(columns, ["address", "adresse", "location", "lieu"]),
                "GeocodedAddress": self._find_column_by_keywords(columns, ["geocoded", "adresse_geocodee"]),
            }
            for widget_name, column_name in optional_columns.items():
                if column_name:
                    columns_mapping[widget_name] = column_name

            intents.append(
                VisualIntent(
                    kind="geo",
                    source_table=table_name,
                    source_columns=list(columns_mapping.values()),
                    insight_refs=[],
                    priority=0.68,
                    confidence=0.83,
                    presentation="geo_page",
                    supported_widgets=[],
                    premium_widgets=["map"],
                    preferred_widget="map",
                    title=f"Carte {table_name}",
                    narrative=f"Carte géographique générée depuis {table_name}.",
                    metadata={
                        "columns_mapping": columns_mapping,
                        "access": "read table",
                    },
                )
            )
        return intents

    def _find_coordinate_columns(
        self,
        table_name: str,
        columns: list[str],
        profile: DataProfile,
    ) -> tuple[str | None, str | None]:
        lat_candidates = self._find_numeric_columns_by_keywords(
            table_name,
            columns,
            profile,
            ["latitude", "lat", "y_coord", "coord_y"],
        )
        lon_candidates = self._find_numeric_columns_by_keywords(
            table_name,
            columns,
            profile,
            ["longitude", "long", "lng", "lon", "x_coord", "coord_x"],
        )
        lat_col = lat_candidates[0] if lat_candidates else None
        lon_col = lon_candidates[0] if lon_candidates else None
        if lat_col == lon_col:
            return None, None
        return lat_col, lon_col

    def _find_numeric_columns_by_keywords(
        self,
        table_name: str,
        columns: list[str],
        profile: DataProfile,
        keywords: list[str],
    ) -> list[str]:
        matches: list[str] = []
        for column in columns:
            normalized = self._normalize_token(column)
            if not any(keyword in normalized for keyword in keywords):
                continue
            stat = profile.stats.get(f"{table_name}.{column}", {})
            if "avg" in stat:
                matches.append(column)
        return matches

    def _find_label_column(
        self,
        table_name: str,
        columns: list[str],
        profile: DataProfile,
        *,
        exclude: set[str],
    ) -> str | None:
        preferred = self._find_column_by_keywords(
            columns,
            ["name", "nom", "label", "title", "site", "city", "ville", "lieu"],
            exclude=exclude,
        )
        if preferred:
            return preferred

        for column in columns:
            if column in exclude:
                continue
            stat = profile.stats.get(f"{table_name}.{column}", {})
            if "avg" not in stat and not self._looks_identifier(column):
                return column
        return None

    def _find_column_by_keywords(
        self,
        columns: list[str],
        keywords: list[str],
        *,
        exclude: set[str] | None = None,
    ) -> str | None:
        exclude = exclude or set()
        for column in columns:
            if column in exclude:
                continue
            normalized = self._normalize_token(column)
            if any(keyword in normalized for keyword in keywords):
                return column
        return None

    def _looks_identifier(self, column: str) -> bool:
        normalized = self._normalize_token(column)
        return any(token in normalized for token in ["id", "code", "uuid", "matricule"])

    def _normalize_token(self, value: str) -> str:
        return "".join(ch.lower() for ch in value if ch.isalnum() or ch == "_")

    def _build_trend_intents(
        self,
        insights: InsightReport,
        profile: DataProfile,
    ) -> list[VisualIntent]:
        intents: list[VisualIntent] = []
        seen: set[tuple[str, str]] = set()
        for idx, insight in enumerate(insights.insights):
            if insight.type != "trend":
                continue
            pair = (insight.table, insight.col)
            if pair in seen:
                continue
            seen.add(pair)
            source_columns = [insight.col]
            stats_key_prefix = f"{insight.table}."
            numeric_columns = [
                key.removeprefix(stats_key_prefix)
                for key, stat in profile.stats.items()
                if key.startswith(stats_key_prefix)
                and "avg" in stat and key.removeprefix(stats_key_prefix) != insight.col
            ]
            if numeric_columns:
                source_columns.append(numeric_columns[0])
            intents.append(
                VisualIntent(
                    kind="trend",
                    source_table=insight.table,
                    source_columns=source_columns,
                    insight_refs=[idx],
                    priority=max(0.5, 1.0 - ((insight.priority - 1) * 0.12)),
                    confidence=0.8,
                    presentation="hero_chart" if idx == 0 else "secondary_chart",
                    supported_widgets=["chart"],
                    premium_widgets=["advanced_chart"],
                    preferred_widget="chart",
                    title=insight.finding,
                    narrative=insight.finding,
                    metadata={"time_column": insight.col},
                )
            )
        return intents

    def _build_narrative_intents(
        self,
        insights: InsightReport,
        narrative: str | None = None,
    ) -> list[VisualIntent]:
        if not insights.insights:
            return []

        all_indices = list(range(len(insights.insights)))
        primary_table = insights.insights[0].table
        all_cols = [ins.col for ins in insights.insights]

        content = narrative if narrative else self._build_fallback_narrative(insights.insights)

        return [
            VisualIntent(
                kind="narrative",
                source_table=primary_table,
                source_columns=all_cols,
                insight_refs=all_indices,
                priority=0.7,
                confidence=0.75,
                presentation="narrative_block",
                supported_widgets=[],
                premium_widgets=["markdown"],
                preferred_widget="markdown",
                title="Resume analytique",
                narrative=content,
                metadata={
                    "content_column": "Content",
                    "table_name": "Narrative_Summary",
                },
            )
        ]

    def _build_fallback_narrative(self, insights: list[Any]) -> str:
        lines = ["# Résumé analytique", ""]
        for insight in sorted(insights, key=lambda i: i.priority):
            lines.append(f"- **{insight.table} / {insight.col}** : {insight.finding}")
        return "\n".join(lines)

    def _build_entity_detail_intents(
        self,
        classification: ClassificationResult,
    ) -> list[VisualIntent]:
        if not classification.table_mapping:
            return []

        primary_table = next(iter(classification.table_mapping.values()))
        return [
            VisualIntent(
                kind="entity_detail",
                source_table=primary_table,
                source_columns=[],
                insight_refs=[],
                priority=0.45,
                confidence=0.7,
                presentation="detail_page",
                supported_widgets=["card_list", "form"],
                premium_widgets=[],
                preferred_widget="card_list",
                title=f"Detail {primary_table}",
                narrative=None,
                metadata={},
            )
        ]