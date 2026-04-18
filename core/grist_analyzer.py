"""Analyzer pour documents Grist existants.

Récupère la structure (tables, colonnes) et les données (records)
d'un document Grist existant via l'API REST.
"""

from typing import Dict, List, Any
from collections import Counter
from core.grist_api import GristAPI


class GristDocumentInfo:
    """Représentation complète d'un document Grist pour analyse."""

    def __init__(self, doc_id: str, tables: List[Dict[str, Any]]):
        self.doc_id = doc_id
        self.tables: Dict[str, Dict[str, Any]] = {}

        for table_info in tables:
            table_id = table_info["id"]
            self.tables[table_id] = {
                "id": table_id,
                "label": table_info.get("label", table_id),
                "columns": table_info.get("columns", []),
                "records": table_info.get("records", []),
                "record_count": table_info.get("record_count", len(table_info.get("records", []))),
                "stats": table_info.get("stats", {}),
            }

    def get_table(self, table_id: str) -> Dict[str, Any]:
        """Récupérer les infos d'une table."""
        return self.tables.get(table_id, {})

    def get_table_names(self) -> List[str]:
        """Liste des IDs de tables."""
        return list(self.tables.keys())


class GristAnalyzer:
    """Analyse un document Grist existant.

    Récupère:
    - Structure: tables, colonnes, types
    - Données: échantillon de records par table
    - Stats: valeurs uniques, min/max, distributions
    """

    DEFAULT_SAMPLE_SIZE = 50

    def __init__(self, grist_api: GristAPI):
        self.grist_api = grist_api

    def analyze(
        self,
        doc_id: str,
        sample_size: int = DEFAULT_SAMPLE_SIZE,
    ) -> GristDocumentInfo:
        """Analyser un document Grist complet.

        Args:
            doc_id: Identifiant du document Grist
            sample_size: Nombre de records à récupérer par table

        Returns:
            GristDocumentInfo avec structure et données
        """
        # 1. Récupérer la structure des tables
        tables = self.grist_api.get_tables(doc_id)
        info = GristDocumentInfo(doc_id, tables)

        # 2. Pour chaque table, récupérer colonnes + records
        for table_id in info.get_table_names():
            # Fetch column definitions (get_tables() does not include them)
            columns = self.grist_api.get_columns(doc_id, table_id)
            info.tables[table_id]["columns"] = columns

            records = self.grist_api.get_records(
                doc_id, table_id, limit=sample_size
            )
            info.tables[table_id]["records"] = records
            info.tables[table_id]["record_count"] = len(records)

            # 3. Calculer des stats simples par colonne
            info.tables[table_id]["stats"] = self._compute_stats(
                records, info.tables[table_id]["columns"]
            )

        return info

    @staticmethod
    def _compute_stats(
        records: List[Dict[str, Any]],
        columns: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Calculer des statistiques simples par colonne.

        Pour chaque colonne:
        - nombre de valeurs non-null
        - nombre de valeurs uniques
        - min/max pour les nombres
        - valeurs les plus fréquentes pour le texte
        """
        stats: Dict[str, Dict[str, Any]] = {}

        # Collecter les valeurs par colonne
        col_values: Dict[str, List[Any]] = {}
        for col in columns:
            col_id = col["id"]
            col_values[col_id] = []

        for record in records:
            fields = record.get("fields", {})
            for col_id, values in col_values.items():
                val = fields.get(col_id)
                if val is not None:
                    values.append(val)

        # Calculer stats par colonne
        for col in columns:
            col_id = col["id"]
            values = col_values.get(col_id, [])
            non_null_count = len(values)

            stat: Dict[str, Any] = {
                "non_null_count": non_null_count,
                "null_count": len(records) - non_null_count,
                "unique_count": len(set(str(v) for v in values)),
            }

            # Min/max pour les nombres
            numeric_values = [
                v for v in values
                if isinstance(v, (int, float))
            ]
            if numeric_values:
                stat["min"] = min(numeric_values)
                stat["max"] = max(numeric_values)
                stat["avg"] = sum(numeric_values) / len(numeric_values)

            # Top values pour le texte
            text_values = [
                v for v in values
                if isinstance(v, str) and not v.isdigit()
            ]
            if text_values:
                counter = Counter(str(v) for v in text_values)
                stat["top_values"] = counter.most_common(10)

            stats[col_id] = stat

        return stats
