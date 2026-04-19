"""Agent 1 - Data Analyzer.

Converts an Excel file into a DataProfile:
- Markdown summary (via markitdown) for LLM consumption
- Per-column statistics (via pandas) for insight extraction
- Apparent foreign key detection between sheets

DataProfile feeds Agents 2, 3, and 4 of the pipeline.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from markitdown import MarkItDown

from config import Settings


@dataclass
class DataProfile:
    """Structured output of DataAnalyzer.analyze()."""

    sheets: list[str]
    columns: dict[str, list[str]]        # sheet -> column names (exact)
    stats: dict[str, dict[str, Any]]     # "Sheet.Col" -> stat dict
    apparent_fk: list[dict[str, str]]    # [{from, to}]
    markdown_summary: str                # for LLM markdown prompt section
    summary_tables: list[dict[str, Any]] = field(default_factory=list)

    def as_prompt_context(self) -> str:
        """Serialize the profile into structured text for LLM prompt injection."""
        lines = [
            f"Sheets disponibles : {self.sheets}",
            "",
        ]
        for sheet, cols in self.columns.items():
            lines.append(f"Colonnes de '{sheet}' : {cols}")
        lines.append("")
        if self.apparent_fk:
            lines.append("Relations detectees :")
            for fk in self.apparent_fk:
                lines.append(f"  {fk['from']} -> {fk['to']}")
            lines.append("")
        if self.summary_tables:
            lines.append("Tables de synthese :")
            for table in self.summary_tables:
                lines.append(
                    f"  {table['name']}: {table['source_table']} / {table['group_by']} x {table['metric']}"
                )
            lines.append("")
        lines.append("Statistiques par colonne (JSON) :")
        lines.append(json.dumps(self.stats, ensure_ascii=False, default=str))
        return "\n".join(lines)

    def to_json(self) -> str:
        """Serialize the profile to JSON for LLM guided_json consumption."""
        return json.dumps(
            {
                "sheets": self.sheets,
                "columns": self.columns,
                "stats": self.stats,
                "apparent_fk": self.apparent_fk,
                "summary_tables": self.summary_tables,
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "DataProfile":
        """Deserialize a DataProfile from JSON string."""
        data = json.loads(json_str)
        return cls(
            sheets=data["sheets"],
            columns=data["columns"],
            stats=data["stats"],
            apparent_fk=data["apparent_fk"],
            markdown_summary="",  # not needed for agent pipeline
            summary_tables=data.get("summary_tables", []),
        )


class DataAnalyzer:
    """Analyse un fichier Excel et produit un DataProfile."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._md = MarkItDown()

    def analyze(self, file_path: str) -> DataProfile:
        """Analyze an Excel file and return a DataProfile.

        Args:
            file_path: Path to the .xlsx file

        Returns:
            DataProfile with markdown, stats, columns, apparent Fks
        """
        # Markdown summary via markitdown
        try:
            markdown_summary = self._md.convert(file_path).text_content
        except Exception:
            markdown_summary = self._fallback_markdown(file_path)

        # Load all sheets with pandas
        sheets_data: dict[str, pd.DataFrame] = pd.read_excel(
            file_path, sheet_name=None
        )

        sheets = list(sheets_data.keys())
        columns: dict[str, list[str]] = {
            sheet: list(df.columns) for sheet, df in sheets_data.items()
        }
        stats = self._compute_stats(sheets_data)
        apparent_fk = self._detect_fk(sheets_data)
        summary_tables = self._compute_summary_tables(sheets_data)

        return DataProfile(
            sheets=sheets,
            columns=columns,
            stats=stats,
            apparent_fk=apparent_fk,
            markdown_summary=markdown_summary,
            summary_tables=summary_tables,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _safe_summary_token(self, text: str) -> str:
        """Normalize a label to a compact ASCII token."""
        nfkd = unicodedata.normalize("NFKD", str(text))
        ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
        ascii_text = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_")
        return ascii_text or "Col"

    def _is_identifier_like(self, series: pd.Series, col_name: str) -> bool:
        """Return True when a column behaves like an identifier instead of a metric."""
        col_lower = str(col_name).lower()
        if any(token in col_lower for token in ["id", "code", "uuid", "matricule"]):
            return True

        non_null = series.dropna()
        if non_null.empty or not pd.api.types.is_numeric_dtype(non_null):
            return False

        unique_ratio = non_null.nunique() / max(len(non_null), 1)
        return unique_ratio > 0.9 and series.is_monotonic_increasing

    def _is_categorical_summary_candidate(self, series: pd.Series, col_name: str) -> bool:
        """Keep categorical columns with enough repetition to form useful groups."""
        del col_name
        if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
            return False
        non_null = series.dropna()
        if non_null.empty:
            return False
        distinct = non_null.nunique()
        return 2 <= distinct <= self.settings.CORRELATION_SUMMARY_MAX_GROUPS

    def _is_numeric_summary_candidate(self, series: pd.Series, col_name: str) -> bool:
        """Keep numeric columns that look like business measures."""
        non_null = series.dropna()
        if non_null.empty or not pd.api.types.is_numeric_dtype(non_null):
            return False
        if self._is_identifier_like(series, col_name):
            return False
        return non_null.nunique() >= 3

    def _score_summary_candidate(
        self,
        df: pd.DataFrame,
        categorical_col: str,
        numeric_col: str,
        summary_df: pd.DataFrame,
    ) -> float:
        """Rank correlation summaries so the most business-relevant float to the top."""
        metric_keywords = [
            "salary", "salaire", "montant", "cout", "cost", "revenue", "ca",
            "score", "note", "budget", "amount", "duree", "duration", "temps",
        ]
        category_keywords = [
            "depart", "service", "team", "type", "statut", "status", "region",
            "site", "manager", "equipe", "category", "categorie",
        ]

        row_count = max(len(df), 1)
        group_count = len(summary_df)
        coverage = summary_df["Effectif"].sum() / row_count
        cat_name = str(categorical_col).lower()
        num_name = str(numeric_col).lower()

        score = coverage * 10
        score += max(0, 6 - abs(group_count - 5))
        score += 4 if any(token in num_name for token in metric_keywords) else 0
        score += 2 if any(token in cat_name for token in category_keywords) else 0
        score += min(group_count, 10) / 10
        return score

    def _build_summary_table(
        self,
        sheet_name: str,
        df: pd.DataFrame,
        categorical_col: str,
        numeric_col: str,
    ) -> dict[str, Any] | None:
        """Build a grouped summary table for one categorical x numeric pair."""
        scoped = df[[categorical_col, numeric_col]].dropna().copy()
        if scoped.empty:
            return None

        grouped = (
            scoped.groupby(categorical_col, dropna=False)[numeric_col]
            .agg([("Effectif", "size"), ("Somme", "sum"), ("Moyenne", "mean"), ("Min", "min"), ("Max", "max")])
            .reset_index()
            .sort_values(by=["Effectif", "Moyenne"], ascending=[False, False])
            .head(self.settings.CORRELATION_SUMMARY_MAX_GROUPS)
        )
        if len(grouped) < 2:
            return None

        metric_token = self._safe_summary_token(numeric_col)
        table_name = "_".join([
            "Corr",
            self._safe_summary_token(sheet_name),
            self._safe_summary_token(categorical_col),
            metric_token,
        ])
        renamed = grouped.rename(columns={
            "Somme": f"{metric_token}_Somme",
            "Moyenne": f"{metric_token}_Moyenne",
            "Min": f"{metric_token}_Min",
            "Max": f"{metric_token}_Max",
        })

        numeric_summary_cols = [
            "Effectif",
            f"{metric_token}_Somme",
            f"{metric_token}_Moyenne",
            f"{metric_token}_Min",
            f"{metric_token}_Max",
        ]
        for col in numeric_summary_cols:
            if col == "Effectif":
                renamed[col] = renamed[col].apply(lambda value: int(value) if pd.notna(value) else None)
            else:
                renamed[col] = renamed[col].apply(lambda value: float(value) if pd.notna(value) else None)

        summary_df = renamed.where(pd.notna(renamed), None)
        return {
            "name": table_name,
            "title": f"{sheet_name} - {categorical_col} x {numeric_col}",
            "source_table": sheet_name,
            "group_by": categorical_col,
            "metric": numeric_col,
            "columns": [
                {"id": categorical_col, "label": categorical_col, "type": "Text"},
                {"id": "Effectif", "label": "Effectif", "type": "Int"},
                {"id": f"{metric_token}_Somme", "label": f"Somme {numeric_col}", "type": "Numeric"},
                {"id": f"{metric_token}_Moyenne", "label": f"Moyenne {numeric_col}", "type": "Numeric"},
                {"id": f"{metric_token}_Min", "label": f"Min {numeric_col}", "type": "Numeric"},
                {"id": f"{metric_token}_Max", "label": f"Max {numeric_col}", "type": "Numeric"},
            ],
            "records": summary_df.to_dict(orient="records"),
            "score": self._score_summary_candidate(df, categorical_col, numeric_col, grouped),
        }

    def _compute_summary_tables(
        self, sheets_data: dict[str, pd.DataFrame]
    ) -> list[dict[str, Any]]:
        """Compute top grouped summaries for categorical x numeric correlations."""
        candidates: list[dict[str, Any]] = []

        for sheet_name, df in sheets_data.items():
            if df.empty or len(df.columns) < 2:
                continue

            categorical_cols = [
                str(col)
                for col in df.columns
                if self._is_categorical_summary_candidate(df[col], str(col))
            ]
            numeric_cols = [
                str(col)
                for col in df.columns
                if self._is_numeric_summary_candidate(df[col], str(col))
            ]

            for categorical_col in categorical_cols:
                for numeric_col in numeric_cols:
                    summary = self._build_summary_table(sheet_name, df, categorical_col, numeric_col)
                    if summary is not None:
                        candidates.append(summary)

        ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
        selected: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str, str]] = set()

        for candidate in ranked:
            pair_key = (
                candidate["source_table"],
                candidate["group_by"],
                candidate["metric"],
            )
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            selected.append({key: value for key, value in candidate.items() if key != "score"})
            if len(selected) >= self.settings.CORRELATION_SUMMARY_MAX_TABLES:
                break

        return selected

    def _compute_stats(
        self, sheets_data: dict[str, pd.DataFrame]
    ) -> dict[str, dict[str, Any]]:
        """Calculate statistics per column."""
        stats: dict[str, dict[str, Any]] = {}
        for sheet, df in sheets_data.items():
            for col in df.columns:
                key = f"{sheet}.{col}"
                series = df[col].dropna()
                entry: dict[str, Any] = {
                    "non_null": int(series.size),
                    "null": int(df[col].isna().sum()),
                    "unique": int(series.nunique()),
                }
                if pd.api.types.is_numeric_dtype(series) and not series.empty:
                    entry["min"] = float(series.min())
                    entry["max"] = float(series.max())
                    entry["avg"] = float(series.mean())
                else:
                    top = series.value_counts().head(self.settings.STATS_TOP_VALUES).index.tolist()
                    entry["top"] = [str(v) for v in top]
                stats[key] = entry
        return stats

    def _detect_fk(
        self, sheets_data: dict[str, pd.DataFrame]
    ) -> list[dict[str, str]]:
        """Detect apparent foreign keys between sheets.

        Heuristics:
        - Column "ID_X" in sheet B -> look for sheet named "X"
        - Column with the same name in two different sheets
        """
        fk: list[dict[str, str]] = []
        sheet_names = list(sheets_data.keys())

        for sheet, df in sheets_data.items():
            for col in df.columns:
                col_upper = str(col).upper()
                # Heuristic 1: "ID_X" -> look for sheet named "X"
                if col_upper.startswith("ID_"):
                    suffix = col_upper[3:]  # e.g. "EMPLOYE" from "ID_EMPLOYE"
                    for other in sheet_names:
                        if other.upper().startswith(suffix) or suffix in other.upper():
                            fk.append({
                                "from": f"{sheet}.{col}",
                                "to": f"{other}.ID",
                            })
                # Heuristic 2: exact column name exists in another sheet primary col
                if col_upper == "ID":
                    continue
                for other, other_df in sheets_data.items():
                    if other == sheet:
                        continue
                    if col in other_df.columns:
                        fk.append({
                            "from": f"{sheet}.{col}",
                            "to": f"{other}.{col}",
                        })
        # Deduplicate
        seen = set()
        unique_fk = []
        for item in fk:
            key = (item["from"], item["to"])
            if key not in seen:
                seen.add(key)
                unique_fk.append(item)
        return unique_fk

    def _fallback_markdown(self, file_path: str) -> str:
        """Fallback: generate Markdown tables using pandas if markitdown fails."""
        try:
            sheets_data = pd.read_excel(file_path, sheet_name=None)
            parts = []
            for sheet, df in sheets_data.items():
                parts.append(f"## {sheet}\n")
                parts.append(df.head(self.settings.MARKITDOWN_MAX_ROWS).to_markdown(index=False))
                parts.append("\n")
            return "\n".join(parts)
        except Exception:
            return f"# {file_path}\n(Markdown extraction failed)"
