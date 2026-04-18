"""Analyseur de structure pour préparation du prompt LLM.

Prend un GristDocumentInfo et génère un prompt structuré
pour le LLM qui analysera le document et suggérera
des formules, changements de colonnes, et recommandations.
"""

import json
from typing import Dict, List, Any, Optional

from core.grist_analyzer import GristDocumentInfo


GRIST_ANALYZER_SYSTEM_PROMPT = """You are an expert Grist database consultant. Your task is to analyze a Grist document structure and data, then suggest optimal configurations.

## What you receive:
- Document name and list of tables
- For each table: columns (id, type, label), sample records, and statistics
- A user request describing what they want to achieve

## Your job:
1. Analyze the data types, distributions, and relationships
2. Suggest useful computed columns with Grist formulas
3. Suggest column type improvements (e.g., convert text to Choice)
4. Recommend widgets/charts/forms appropriate for the data

## Grist Formula Reference:
- Arithmetic: `@ColumnA + @ColumnB`, `@ColumnA * @ColumnB`
- Date: `FormatDate(@DateColumn, "MMM YYYY")`, `Month(@DateColumn)`
- Text: `Trim(@Column)`, `Upper(@Column)`, `Concatenate(@A, " ", @B)`
- Conditional: `If(@Condition, "Yes", "No")`
- Lookup: `Lookup(RefColumn, "TargetTable", "TargetColumn")`
- Aggregation: `Sum(Table.RefColumn->TargetColumn)`, `Count(Table.RefColumn)`
- Number: `Round(@Column, 2)`, `Abs(@Column)`, `Max(@A, @B)`

## Output Format:
Return ONLY valid JSON with this exact structure:

{
  "formulas": [
    {
      "table": "TableName",
      "column": "NewColumnName",
      "type": "Numeric|Text|Date|Integer",
      "formula": "Grist formula here",
      "label": "Display Label"
    }
  ],
  "columnChanges": [
    {
      "table": "TableName",
      "column": "ExistingColumn",
      "newType": "Choice|Toggle|Date|Integer|Numeric|Text|Reference",
      "choices": ["option1", "option2"],
      "refTable": "OtherTableId"
    }
  ],
  "recommendations": [
    {
      "widget": "Chart|Form|Card|Card List|Calendar",
      "description": "Human-readable description in French if user requested French",
      "table": "TableName",
      "x": "ColumnForXAxis",
      "y": "ColumnForYAxis",
      "aggregation": "sum|avg|count|min|max"
    }
  ]
}

Rules:
- Only suggest formulas that make sense for the data types
- For formulas, use @Column syntax for same-table columns
- For cross-table lookups, use Lookup() syntax
- Recommendations should be practical and data-appropriate
- Use French descriptions if the user request is in French
- Do NOT include widgets that require undocumented API access
- Keep recommendations actionable and specific
- For Reference columnChanges, always include "refTable" with the exact table ID (e.g. "Employes")
- "choices" is only required for Choice/ChoiceList types; omit it for other types
- "refTable" is only required for Reference type; omit it for other types
"""


class SchemaAnalyzer:
    """Analyse un document Grist et prépare le prompt LLM."""

    def __init__(
        self,
        document_info: GristDocumentInfo,
        user_request: str,
    ):
        self.document_info = document_info
        self.user_request = user_request

    def build_prompt(self) -> str:
        """Construire le prompt complet pour le LLM.

        Inclut:
        - Structure des tables (colonnes, types)
        - Échantillons de données (premières 5 lignes)
        - Statistiques par colonne
        - Request utilisateur
        """
        parts = []
        parts.append(f"Document Grist: {self.document_info.doc_id}")
        parts.append(f"Nombre de tables: {len(self.document_info.tables)}")
        parts.append("")

        for table_id, table_info in self.document_info.tables.items():
            parts.append(f"=== TABLE: {table_info['label']} ({table_id}) ===")
            parts.append(f"Records échantillon: {table_info.get('record_count', 0)}")
            parts.append("")

            # Colonnes
            parts.append("Colonnes:")
            for col in table_info["columns"]:
                col_id = col["id"]
                col_type = col.get("fields", {}).get("type", "Unknown")
                col_label = col.get("fields", {}).get("label", col_id)
                parts.append(f"  - {col_id} ({col_label}): {col_type}")

            # Stats
            stats = table_info.get("stats", {})
            if stats:
                parts.append("\nStatistiques:")
                for col_id, col_stats in stats.items():
                    parts.append(f"  {col_id}:")
                    parts.append(
                        f"    Non-null: {col_stats['non_null_count']}, "
                        f"Null: {col_stats['null_count']}, "
                        f"Unique: {col_stats['unique_count']}"
                    )
                    if "min" in col_stats:
                        parts.append(
                            f"    Min: {col_stats['min']}, "
                            f"Max: {col_stats['max']}, "
                            f"Avg: {col_stats['avg']:.2f}"
                        )
                    if "top_values" in col_stats:
                        top = col_stats["top_values"][:5]
                        parts.append(
                            f"    Top valeurs: {top}"
                        )

            # Échantillon de records
            records = table_info.get("records", [])[:5]
            if records:
                parts.append("\nÉchantillon (5 premières lignes):")
                for i, record in enumerate(records):
                    fields = record.get("fields", {})
                    parts.append(f"  Ligne {i + 1}: {json.dumps(fields, default=str)}")

            parts.append("")

        parts.append(f"Request utilisateur: {self.user_request}")
        parts.append(
            "\nAnalyse cette structure et suggère des formules, "
            "changements de colonnes, et recommandations de widgets."
        )
        parts.append(
            "\nRetourne UNIQUEMENT du JSON valide avec la structure: "
            "formulas, columnChanges, recommendations."
        )

        return "\n".join(parts)

    def build_messages(self) -> List[Dict[str, str]]:
        """Construit les messages pour l'appel API vLLM."""
        prompt = self.build_prompt()
        return [
            {"role": "system", "content": GRIST_ANALYZER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
