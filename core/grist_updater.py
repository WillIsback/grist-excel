"""Updateur pour appliquer la config LLM dans un document Grist.

Applique les formules et changements de colonnes suggérés
par le LLM via l'API REST Grist.
"""

import json
from typing import Dict, Any
from core.grist_api import GristAPI


class GristUpdater:
    """Applique les suggestions du LLM dans un document Grist."""

    def __init__(self, grist_api: GristAPI):
        self.grist_api = grist_api

    def apply_config(
        self,
        doc_id: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Appliquer la config LLM complète.

        Args:
            doc_id: Identifiant du document Grist
            config: JSON de config généré par le LLM

        Returns:
            Résumé de ce qui a été appliqué
        """
        summary = {
            "formulas_applied": 0,
            "column_changes_applied": 0,
            "errors": [],
        }

        # 1. Appliquer les formules
        for formula in config.get("formulas", []):
            try:
                self._apply_formula(doc_id, formula)
                summary["formulas_applied"] += 1
            except Exception as e:
                summary["errors"].append(
                    f"Erreur formule {formula.get('table', '?')}.{formula.get('column', '?')}: {e}"
                )

        # 2. Appliquer les changements de colonnes
        for change in config.get("columnChanges", []):
            try:
                self._apply_column_change(doc_id, change)
                summary["column_changes_applied"] += 1
            except Exception as e:
                summary["errors"].append(
                    f"Erreur colonne {change.get('table', '?')}.{change.get('column', '?')}: {e}"
                )

        return summary

    def _apply_formula(
        self,
        doc_id: str,
        formula_config: Dict[str, Any],
    ) -> None:
        """Ajouter une nouvelle colonne avec formule."""
        table = formula_config["table"]
        column = formula_config["column"]
        formula = formula_config["formula"]
        col_type = formula_config.get("type", "Text")
        label = formula_config.get("label", column)

        # Normaliser le type Grist
        normalized_type = GristAPI.normalize_grist_type(col_type)

        col_def = {
            "id": column,
            "fields": {
                "type": normalized_type,
                "formula": formula,
                "isFormula": True,
                "label": label,
            },
        }
        try:
            self.grist_api.add_columns(doc_id, table, [col_def])
        except Exception:
            # Column already exists — update it instead
            self.grist_api.patch_columns(doc_id, table, [col_def])

    def _apply_column_change(
        self,
        doc_id: str,
        change_config: Dict[str, Any],
    ) -> None:
        """Modifier le type d'une colonne existante."""
        table = change_config["table"]
        column = change_config["column"]
        new_type = change_config["newType"]

        normalized = GristAPI.normalize_grist_type(new_type)

        # Reference columns need "Ref:TableId" format, not plain "Reference"
        if normalized == "Reference":
            ref_table = change_config.get("refTable", "")
            if not ref_table:
                raise ValueError(
                    f"columnChange for {table}.{column} has type Reference "
                    "but is missing 'refTable'"
                )
            normalized = f"Ref:{ref_table}"

        fields: Dict[str, Any] = {"type": normalized}

        # Gérer les choices
        if "choices" in change_config:
            fields["widgetOptions"] = json.dumps({
                "choices": change_config["choices"],
            })

        self.grist_api.patch_columns(doc_id, table, [
            {"id": column, "fields": fields},
        ])

    @staticmethod
    def print_recommendations(config: Dict[str, Any]) -> None:
        """Afficher les recommandations widgets sous forme lisible."""
        recommendations = config.get("recommendations", [])
        if not recommendations:
            print("  Aucune recommandation de widgets.")
            return

        print(f"\n{'=' * 60}")
        print("RECOMMANDATIONS DE WIDGETS/VUES")
        print(f"{'=' * 60}")
        print(
            "Note: Ces recommandations doivent être appliquées manuellement "
            "dans Grist (l'API REST ne supporte pas la création de widgets)."
        )
        print()

        for i, rec in enumerate(recommendations, 1):
            widget_type = rec.get("widget", "Unknown")
            desc = rec.get("description", "Sans description")
            table = rec.get("table", "?")
            print(f"  {i}. [{widget_type}] {desc}")
            print(f"     Table: {table}")
            if "x" in rec:
                print(f"     Axe X: {rec['x']}")
            if "y" in rec:
                print(f"     Axe Y: {rec['y']}")
            if "aggregation" in rec:
                print(f"     Agrégation: {rec['aggregation']}")
            print()
