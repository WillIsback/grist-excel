"""Grist Importer — Excel → Grist via API.

Lit chaque feuille du fichier Excel et crée:
1. Une table Grist avec les noms de colonnes exacts
2. Les types de colonnes inférés (Text, Int, Numeric, Date, Toggle)
3. Tous les records (lignes)

Utilise uniquement l'API REST Grist.
"""

import os
import math
import re
import warnings
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import pandas as pd
from core.grist_api import GristAPI, GristConnectionError


def _normalize_accent(text: str) -> str:
    """Remove accents from text (É->E, è->e, etc.)."""
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def _safe_table_id(name: str) -> str:
    """Créer un identifiant de table sûr pour Grist (ASCII only)."""
    table_id = _normalize_accent(name)
    table_id = re.sub(r'\s+', '_', table_id)
    if not table_id or table_id[0].isdigit():
        table_id = 'Table_' + table_id
    return table_id


def _safe_col_id(name: str) -> str:
    """Créer un identifiant de colonne sûr pour Grist (ASCII only)."""
    col_id = _normalize_accent(name)
    col_id = re.sub(r'\s+', '_', col_id)
    if not col_id or col_id[0].isdigit():
        col_id = 'Col_' + col_id
    return col_id


def _infer_grist_type(series: pd.Series) -> str:
    """Inférer le type Grist à partir d'une série pandas."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return "Text"

    # Check boolean/toggle first (before numeric, to catch "oui"/"non")
    try:
        bool_vals = {"true", "false", "vrai", "faux", "oui", "non", "1", "0"}
        if all(str(v).lower() in bool_vals for v in non_null):
            return "Toggle"
    except (ValueError, TypeError):
        pass

    # Check numeric float — BEFORE datetime checks
    # (prevents large ints being read as timestamps)
    try:
        floats = [float(v) for v in non_null if not pd.isna(v)]
        if floats:
            # Check if all values are integers
            if all(float(v).is_integer() for v in floats):
                # Return "Int" only if all values are small integers (≤ 1000)
                # This avoids mis-classifying large numeric measurements like salaries
                if all(abs(float(v)) <= 1000 for v in floats):
                    return "Int"
            return "Numeric"
    except (ValueError, TypeError):
        pass

    # Check datetime — only if values are non-numeric strings
    # (guards against pandas treating large integers as nanosecond timestamps)
    try:
        if all(isinstance(v, str) for v in non_null):
            parsed = pd.to_datetime(non_null, errors="coerce")
            if parsed.notna().all():
                is_date_only = all(
                    not (hasattr(v, "hour") and v.hour)
                    for v in non_null.head(100)
                )
                return "Date" if is_date_only else "DateTime"
    except (ValueError, TypeError):
        pass

    return "Text"


def _clean_value(v: Any) -> Any:
    """Nettoyer une valeur pour Grist."""
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, pd.Timedelta):
        return str(v)
    if pd.isna(v):
        return None
    return v


class GristImporter:
    """Importe un fichier Excel dans Grist via l'API REST."""

    def __init__(self, api: GristAPI):
        self.api = api

    def import_excel(self, file_path: str) -> str:
        """Uploader un fichier Excel et retourner le docId cree avec toutes les tables.

        Etapes:
        1. Creer un document vide
        2. Pour chaque feuille: creer table + colonnes + records
        3. Retourner le docId

        Args:
            file_path: Chemin vers le fichier .xlsx

        Returns:
            docId du document Grist cree

        Raises:
            FileNotFoundError: Si le fichier n'existe pas
            GristConnectionError: Si la creation du document échoue
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Fichier introuvable : {file_path}")

        # Lire toutes les feuilles
        try:
            xls = pd.ExcelFile(file_path)
        except Exception as e:
            raise GristConnectionError(f"Impossible de lire le fichier Excel: {e}")

        # Creer un document vide
        try:
            doc_id = self.api.create_document(name=os.path.basename(file_path).replace('.xlsx', ''))
        except Exception as e:
            raise GristConnectionError(f"Impossible de creer le document: {e}")

        # Grist auto-creates a blank Table1 on every new doc — remove it
        self.api.delete_table(doc_id, "Table1")

        # Importer chaque feuille
        for sheet_name in xls.sheet_names:
            try:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                if df.empty:
                    continue
                self._import_sheet(doc_id, sheet_name, df)
            except Exception as e:
                print(f"  Erreur feuille '{sheet_name}': {e}")

        return doc_id

    def _import_sheet(self, doc_id: str, sheet_name: str, df: pd.DataFrame) -> None:
        """Creer une table Grist pour une feuille Excel."""
        # Utiliser _safe_table_id qui normalise les accents en ASCII
        table_id = _safe_table_id(sheet_name)

        # Creer les colonnes
        columns = []
        for col in df.columns:
            col_id = _safe_col_id(col)
            grist_type = _infer_grist_type(df[col])
            columns.append({
                "id": col_id,
                "fields": {
                    "type": grist_type,
                    "label": col,
                }
            })

        # Creer la table avec les colonnes
        self.api.create_table(doc_id, table_id, columns)

        # Importer les records
        records = []
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                col_id = _safe_col_id(col)
                record[col_id] = _clean_value(row[col])
            records.append(record)

        if records:
            self.api.add_records(doc_id, table_id, records)
