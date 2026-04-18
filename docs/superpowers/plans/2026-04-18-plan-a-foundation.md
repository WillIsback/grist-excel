# Data-to-Dashboard — Plan A: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data extraction and Grist upload foundation that the LLM agent pipeline (Plan B) and archetype engine (Plan C) depend on.

**Architecture:** Four self-contained pieces: (1) GristAPI gains `upload_excel()` and `apply_actions()` — the two new primitives needed by the full pipeline; (2) `DataAnalyzer` converts an Excel file to a `DataProfile` (Markdown summary + per-column stats + FK detection) using markitdown for prose and pandas for stats; (3) `GristImporter` wraps the upload and verifies sheet-level table creation; (4) `config.py` and `requirements.txt` gain the new settings and dependency.

**Tech Stack:** Python 3.11, pandas, openpyxl, markitdown, requests, pytest, unittest.mock

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `core/grist_api.py` | Add `upload_excel()` and `apply_actions()` |
| Create | `core/data_analyzer.py` | Excel → DataProfile (Markdown + stats + FK) |
| Create | `core/grist_importer.py` | Upload xlsx → verified docId |
| Modify | `config.py` | Add `MARKITDOWN_MAX_ROWS` |
| Modify | `requirements.txt` | Add `markitdown`, `tabulate` |
| Create | `tests/test_grist_api_actions.py` | Tests for new GristAPI methods |
| Create | `tests/test_data_analyzer.py` | Tests for DataAnalyzer |
| Create | `tests/test_grist_importer.py` | Tests for GristImporter |

---

### Task 1: GristAPI — `upload_excel()` and `apply_actions()`

**Files:**
- Modify: `core/grist_api.py` (add two methods after `find_document()`, ~line 375)
- Create: `tests/test_grist_api_actions.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_grist_api_actions.py`:

```python
"""Tests for GristAPI.upload_excel() and GristAPI.apply_actions()."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from core.grist_api import GristAPI, GristAPIError


@pytest.fixture
def mock_session():
    with patch("requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        yield session


@pytest.fixture
def api(mock_session):
    a = GristAPI("http://localhost:8484", "test-key")
    a._org_id = "2"
    return a


def _resp(data, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = data
    r.raise_for_status.return_value = None
    return r


class TestUploadExcel:
    def test_returns_doc_id_string(self, api, mock_session, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"PK\x03\x04fake-xlsx-content")
        mock_session.request.return_value = _resp("new~abc123~1")

        doc_id = api.upload_excel(str(xlsx))

        assert doc_id == "new~abc123~1"

    def test_posts_to_api_docs_with_xlsx_content_type(self, api, mock_session, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        content = b"PK\x03\x04binary-content"
        xlsx.write_bytes(content)
        mock_session.request.return_value = _resp("new~abc123~1")

        api.upload_excel(str(xlsx))

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "/api/docs" in call_kwargs[0][1]
        headers = call_kwargs[1].get("headers", {})
        assert "spreadsheetml" in headers.get("Content-Type", "")
        assert call_kwargs[1].get("data") == content

    def test_raises_on_non_string_response(self, api, mock_session, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        mock_session.request.return_value = _resp({"error": "bad"})

        with pytest.raises(GristAPIError):
            api.upload_excel(str(xlsx))


class TestApplyActions:
    def test_posts_actions_to_apply_endpoint(self, api, mock_session):
        mock_session.request.return_value = _resp({"results": []})
        actions = [["AddRecord", "_grist_Views", None, {"name": "Dashboard"}]]

        result = api.apply_actions("doc123", actions)

        call_kwargs = mock_session.request.call_args
        assert call_kwargs[0][0] == "POST"
        assert "doc123/apply" in call_kwargs[0][1]
        body = call_kwargs[1].get("json", {})
        assert body == {"actions": actions}

    def test_returns_response_json(self, api, mock_session):
        mock_session.request.return_value = _resp({"results": [1, 2]})

        result = api.apply_actions("doc123", [])

        assert result == {"results": [1, 2]}
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_grist_api_actions.py -v 2>&1 | head -20
```

Expected: `AttributeError: 'GristAPI' object has no attribute 'upload_excel'`

- [ ] **Step 3: Add `upload_excel()` and `apply_actions()` to `core/grist_api.py`**

Insert after `find_document()` (around line 375), inside the `GristAPI` class:

```python
# ------------------------------------------------------------------
# Excel Import & Internal Actions
# ------------------------------------------------------------------

def upload_excel(self, file_path: str) -> str:
    """Uploader un fichier Excel et créer un document Grist.

    POST /api/docs (binary xlsx content)

    Args:
        file_path: Chemin absolu ou relatif vers le fichier .xlsx

    Returns:
        docId du document créé (ex: "new~abc123~1")

    Raises:
        GristAPIError: Si la réponse n'est pas un docId string.
    """
    with open(file_path, "rb") as f:
        content = f.read()

    response = self._request_with_retry(
        "POST",
        self._api_url("/api/docs"),
        data=content,
        headers={
            "Content-Type": (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
        },
    )
    doc_id = response.json()
    if not isinstance(doc_id, str):
        raise GristAPIError(200, f"Réponse upload inattendue: {doc_id}")
    return doc_id

def apply_actions(self, doc_id: str, actions: list) -> dict:
    """Appliquer des actions internes Grist à un document.

    POST /api/docs/{docId}/apply
    Body: {"actions": [[actionType, tableId, rowId, fields], ...]}

    Args:
        doc_id: Identifiant du document cible
        actions: Liste d'actions Grist internes

    Returns:
        Réponse JSON de l'API (résultats des actions)
    """
    response = self._request_with_retry(
        "POST",
        self._doc_url(doc_id, "apply"),
        json={"actions": actions},
    )
    return response.json()
```

- [ ] **Step 4: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_grist_api_actions.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Run full suite for regressions**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/grist_api.py tests/test_grist_api_actions.py
git commit -m "feat: add upload_excel() and apply_actions() to GristAPI"
```

---

### Task 2: Dependencies — markitdown + tabulate

**Files:**
- Modify: `requirements.txt`
- Modify: `config.py`

- [ ] **Step 1: Add dependencies**

Add to `requirements.txt`:
```
markitdown[xlsx]>=0.1.0
tabulate>=0.9.0
```

- [ ] **Step 2: Install**

```bash
cd /home/wderue/workspace/grist-excel && pip install "markitdown[xlsx]" tabulate 2>&1 | tail -5
```

Expected: `Successfully installed markitdown-...`

- [ ] **Step 3: Verify markitdown Excel support**

```bash
python3 -c "
from markitdown import MarkItDown
md = MarkItDown()
result = md.convert('samples/employees_rh.xlsx')
print(result.text_content[:500])
"
```

Expected: Markdown tables with headers from the Excel sheets.

- [ ] **Step 4: Add config setting to `config.py`**

Add inside the `Settings` class, after `EXCEL_MAX_ROWS`:

```python
# Data analysis settings
MARKITDOWN_MAX_ROWS: int = 50  # max rows per sheet in Markdown summary
STATS_TOP_VALUES: int = 5      # top N values for categorical stats
```

- [ ] **Step 5: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add requirements.txt config.py
git commit -m "chore: add markitdown and tabulate dependencies; add analysis config settings"
```

---

### Task 3: DataAnalyzer — Excel → DataProfile

**Files:**
- Create: `core/data_analyzer.py`
- Create: `tests/test_data_analyzer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_data_analyzer.py`:

```python
"""Tests for core/data_analyzer.py — DataAnalyzer and DataProfile."""
import pytest
import openpyxl
from pathlib import Path
from core.data_analyzer import DataAnalyzer, DataProfile


@pytest.fixture
def sample_xlsx(tmp_path) -> Path:
    """Create a minimal two-sheet Excel file for testing."""
    wb = openpyxl.Workbook()

    # Sheet 1: Employes
    ws1 = wb.active
    ws1.title = "Employes"
    ws1.append(["ID", "Nom", "Departement", "Salaire"])
    ws1.append([1, "Alice", "IT", 60000])
    ws1.append([2, "Bob", "RH", 45000])
    ws1.append([3, "Carol", "IT", 75000])

    # Sheet 2: Absences (references Employes.ID)
    ws2 = wb.create_sheet("Absences")
    ws2.append(["ID_Employe", "Date_Debut", "Duree_Jours"])
    ws2.append([1, "2024-01-10", 3])
    ws2.append([2, "2024-02-05", 1])

    path = tmp_path / "test.xlsx"
    wb.save(str(path))
    return path


class TestDataProfile:
    def test_sheets_extracted(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        assert "Employes" in profile.sheets
        assert "Absences" in profile.sheets

    def test_columns_extracted(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        assert profile.columns["Employes"] == ["ID", "Nom", "Departement", "Salaire"]
        assert profile.columns["Absences"] == ["ID_Employe", "Date_Debut", "Duree_Jours"]

    def test_numeric_stats_computed(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        sal_stats = profile.stats["Employes.Salaire"]
        assert sal_stats["min"] == 45000
        assert sal_stats["max"] == 75000
        assert sal_stats["avg"] == pytest.approx(60000.0)
        assert sal_stats["non_null"] == 3

    def test_categorical_stats_computed(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        dept_stats = profile.stats["Employes.Departement"]
        assert dept_stats["unique"] == 2
        assert "IT" in dept_stats["top"]
        assert dept_stats["non_null"] == 3

    def test_apparent_fk_detected(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        # Absences.ID_Employe references Employes.ID (suffix match)
        fk_targets = [fk["to"] for fk in profile.apparent_fk]
        assert any("Employes" in t for t in fk_targets)

    def test_markdown_summary_contains_sheet_headers(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        assert "Employes" in profile.markdown_summary
        assert "Absences" in profile.markdown_summary
        assert "Nom" in profile.markdown_summary
        assert "Departement" in profile.markdown_summary

    def test_as_prompt_context_returns_string(self, sample_xlsx):
        profile = DataAnalyzer().analyze(str(sample_xlsx))
        ctx = profile.as_prompt_context()
        assert isinstance(ctx, str)
        assert "sheets" in ctx.lower() or "Employes" in ctx
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_data_analyzer.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'core.data_analyzer'`

- [ ] **Step 3: Implement `core/data_analyzer.py`**

Create `core/data_analyzer.py`:

```python
"""Agent 1 — Data Analyzer.

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
    columns: dict[str, list[str]]        # sheet → column names (exact)
    stats: dict[str, dict[str, Any]]     # "Sheet.Col" → stat dict
    apparent_fk: list[dict[str, str]]    # [{from, to}]
    markdown_summary: str                # for LLM markdown prompt section

    def as_prompt_context(self) -> str:
        """Serialise le profil en texte structuré pour injection dans un prompt LLM."""
        lines = [
            f"Sheets disponibles : {self.sheets}",
            "",
        ]
        for sheet, cols in self.columns.items():
            lines.append(f"Colonnes de '{sheet}' : {cols}")
        lines.append("")
        if self.apparent_fk:
            lines.append("Relations détectées :")
            for fk in self.apparent_fk:
                lines.append(f"  {fk['from']} → {fk['to']}")
            lines.append("")
        lines.append("Statistiques par colonne (JSON) :")
        lines.append(json.dumps(self.stats, ensure_ascii=False, default=str))
        return "\n".join(lines)


class DataAnalyzer:
    """Analyse un fichier Excel et produit un DataProfile."""

    _md = MarkItDown()

    def analyze(self, file_path: str) -> DataProfile:
        """Analyser un fichier Excel et retourner un DataProfile.

        Args:
            file_path: Chemin vers le fichier .xlsx

        Returns:
            DataProfile avec markdown, stats, colonnes, FK apparentes
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
        """Calculer les statistiques par colonne."""
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
        """Détecter les clés étrangères apparentes entre sheets.

        Heuristiques :
        - Colonne "ID_X" dans sheet B → colonne "ID" dans sheet X
        - Colonne avec le même nom dans deux sheets différentes
        """
        fk: list[dict[str, str]] = []
        sheet_names = list(sheets_data.keys())

        for sheet, df in sheets_data.items():
            for col in df.columns:
                col_upper = str(col).upper()
                # Heuristic 1: "ID_X" → look for sheet named "X"
                if col_upper.startswith("ID_"):
                    suffix = col_upper[3:]  # e.g. "EMPLOYE" from "ID_EMPLOYE"
                    for other in sheet_names:
                        if other.upper().startswith(suffix) or suffix in other.upper():
                            fk.append({
                                "from": f"{sheet}.{col}",
                                "to": f"{other}.ID",
                            })
                # Heuristic 2: exact column name exists in another sheet's primary col
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
```

- [ ] **Step 4: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_data_analyzer.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/data_analyzer.py tests/test_data_analyzer.py
git commit -m "feat: add DataAnalyzer — Excel to DataProfile (markitdown + pandas stats)"
```

---

### Task 4: GristImporter — upload + verify

**Files:**
- Create: `core/grist_importer.py`
- Create: `tests/test_grist_importer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_grist_importer.py`:

```python
"""Tests for core/grist_importer.py — GristImporter."""
import pytest
from unittest.mock import MagicMock, patch
from core.grist_importer import GristImporter
from core.grist_api import GristAPI, GristConnectionError


@pytest.fixture
def mock_api():
    api = MagicMock(spec=GristAPI)
    api.upload_excel.return_value = "new~abc123~1"
    api.get_tables.return_value = [
        {"id": "Employes", "fields": {}},
        {"id": "Absences", "fields": {}},
    ]
    return api


class TestGristImporter:
    def test_import_excel_returns_doc_id(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        importer = GristImporter(mock_api)

        doc_id = importer.import_excel(str(xlsx))

        assert doc_id == "new~abc123~1"

    def test_calls_upload_then_get_tables(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        importer = GristImporter(mock_api)

        importer.import_excel(str(xlsx))

        mock_api.upload_excel.assert_called_once_with(str(xlsx))
        mock_api.get_tables.assert_called_once_with("new~abc123~1")

    def test_raises_if_no_tables_after_import(self, mock_api, tmp_path):
        xlsx = tmp_path / "test.xlsx"
        xlsx.write_bytes(b"fake")
        mock_api.get_tables.return_value = []
        importer = GristImporter(mock_api)

        with pytest.raises(GristConnectionError) as exc_info:
            importer.import_excel(str(xlsx))
        assert "aucune table" in str(exc_info.value).lower()

    def test_raises_if_file_not_found(self, mock_api):
        importer = GristImporter(mock_api)

        with pytest.raises(FileNotFoundError):
            importer.import_excel("/nonexistent/path/file.xlsx")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_grist_importer.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'core.grist_importer'`

- [ ] **Step 3: Implement `core/grist_importer.py`**

Create `core/grist_importer.py`:

```python
"""Grist Importer — upload Excel and verify document creation.

Thin layer over GristAPI.upload_excel() that:
1. Validates the file exists
2. Uploads the Excel binary to Grist
3. Verifies the resulting document has at least one table
4. Returns the docId for use by the Archetype Engine
"""

import os
from core.grist_api import GristAPI, GristConnectionError


class GristImporter:
    """Importe un fichier Excel dans Grist et vérifie le résultat."""

    def __init__(self, api: GristAPI):
        self.api = api

    def import_excel(self, file_path: str) -> str:
        """Uploader un fichier Excel et retourner le docId vérifié.

        Args:
            file_path: Chemin vers le fichier .xlsx

        Returns:
            docId du document Grist créé

        Raises:
            FileNotFoundError: Si le fichier n'existe pas
            GristConnectionError: Si le document créé ne contient aucune table
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Fichier introuvable : {file_path}")

        doc_id = self.api.upload_excel(file_path)

        tables = self.api.get_tables(doc_id)
        if not tables:
            raise GristConnectionError(
                f"Import échoué : aucune table trouvée dans le document '{doc_id}'. "
                "Vérifiez que le fichier Excel contient au moins une feuille avec des données."
            )

        return doc_id
```

- [ ] **Step 4: Run tests**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest tests/test_grist_importer.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd /home/wderue/workspace/grist-excel && python3 -m pytest --ignore=venv -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /home/wderue/workspace/grist-excel && git add core/grist_importer.py tests/test_grist_importer.py
git commit -m "feat: add GristImporter — upload Excel and verify table creation"
```
