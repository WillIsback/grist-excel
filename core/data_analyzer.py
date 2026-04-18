"""Agent 1 - Data Analyzer.

Converts an Excel file into a DataProfile:
- Markdown summary (via markitdown) for LLM consumption
- Per-column statistics (via pandas) for insight extraction
- Apparent foreign key detection between sheets

DataProfile feeds Agents 2, 3, and 4 of the pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from markitdown import MarkItDown


@dataclass
class DataProfile:
    """Structured output of DataAnalyzer.analyze()."""

    sheets: list[str]
    columns: dict[str, list[str]]        # sheet -> column names (exact)
    stats: dict[str, dict[str, Any]]     # "Sheet.Col" -> stat dict
    apparent_fk: list[dict[str, str]]    # [{from, to}]
    markdown_summary: str                # for LLM markdown prompt section

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
        )


class DataAnalyzer:
    """Analyse un fichier Excel et produit un DataProfile."""

    _md = MarkItDown()

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

        return DataProfile(
            sheets=sheets,
            columns=columns,
            stats=stats,
            apparent_fk=apparent_fk,
            markdown_summary=markdown_summary,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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
                    top = series.value_counts().head(5).index.tolist()
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
                parts.append(df.head(10).to_markdown(index=False))
                parts.append("\n")
            return "\n".join(parts)
        except Exception:
            return f"# {file_path}\n(Markdown extraction failed)"
