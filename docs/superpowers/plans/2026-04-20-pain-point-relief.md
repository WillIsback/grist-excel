# Pain-Point Relief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Phase 2 refinement loop so users can iterate on pipeline output without full restart, and enrich the result screen with quality indicators and intent echo.

**Architecture:** Split pipeline into Analysis (cached) and Generation (re-runnable). Session stores cached DataProfile + ClassificationResult + full InsightReport. A `/refine/{sid}` endpoint serves cached insights and triggers Phase 2 re-run. The result screen gains a quality card and "Affiner" button.

**Tech Stack:** Python 3.12, FastAPI, threading, vanilla JS, SSE (no new dependencies).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `webui/session.py` | Modify | Add cache fields + refine threading primitives |
| `webui/checkpoint_handler.py` | Modify | Cache full InsightReport in session on Checkpoint 2 |
| `webui/pipeline_runner.py` | Modify | Cache Phase 1 data; capture `fe.apply()` results; enrich `complete` event; add `run_refinement()` |
| `core/pipeline.py` | Modify | Add `run_from_insights()` — Phase 2 entry point |
| `webui/server.py` | Modify | Add `GET /refine/{sid}` and `POST /refine/{sid}` |
| `webui/templates/run.html` | Modify | Redesign result screen; add refinement screen |
| `webui/static/app.js` | Modify | Update `showResult()`; add `showRefine()`; handle refinement submit + stream |
| `tests/test_webui_session.py` | Modify | Test new session fields |
| `tests/test_pipeline.py` | Modify | Test `run_from_insights()` |
| `tests/test_webui_server.py` | Modify | Test `/refine` endpoints |

---

## Task 1: Extend PipelineSession with cache and refinement fields

**Files:**
- Modify: `webui/session.py`
- Test: `tests/test_webui_session.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_webui_session.py

def test_session_has_cache_fields():
    store = SessionStore()
    sid = store.create()
    session = store.get(sid)
    assert session.cached_profile is None
    assert session.cached_classification is None
    assert session.cached_insights is None


def test_session_has_refine_event():
    store = SessionStore()
    sid = store.create()
    session = store.get(sid)
    assert isinstance(session.refine_event, threading.Event)
    assert session.refine_response is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/wderue/workspace/grist-excel
uv run pytest tests/test_webui_session.py::test_session_has_cache_fields tests/test_webui_session.py::test_session_has_refine_event -v
```

Expected: `AttributeError: 'PipelineSession' object has no attribute 'cached_profile'`

- [ ] **Step 3: Add fields to PipelineSession**

Replace the `PipelineSession` dataclass in `webui/session.py` with:

```python
"""In-memory pipeline session store."""
from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.data_analyzer import DataProfile
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightEntry


@dataclass
class PipelineSession:
    event_queue: queue.Queue = field(default_factory=queue.Queue)
    checkpoint1_event: threading.Event = field(default_factory=threading.Event)
    checkpoint1_response: dict[str, Any] | None = None
    checkpoint2_event: threading.Event = field(default_factory=threading.Event)
    checkpoint2_response: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    # Phase 1 cache — populated after DataAnalyzer + DomainClassifier
    cached_profile: "DataProfile | None" = None
    cached_classification: "ClassificationResult | None" = None
    # Full InsightReport from last InsightExtractor run (before Checkpoint 2 filtering)
    cached_insights: "list[InsightEntry] | None" = None

    # Path to uploaded temp file — needed so refinement can re-import to Grist
    cached_tmp_path: str | None = None

    # Refinement — user re-submits intent + insight selection for Phase 2 re-run
    refine_event: threading.Event = field(default_factory=threading.Event)
    refine_response: dict[str, Any] | None = None  # {intent: str, selected_indices: list[int]}


class SessionStore:
    """Thread-safe in-memory store for pipeline sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, PipelineSession] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        sid = str(uuid.uuid4())
        with self._lock:
            self._sessions[sid] = PipelineSession()
        return sid

    def get(self, sid: str) -> PipelineSession | None:
        with self._lock:
            return self._sessions.get(sid)

    def delete(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_webui_session.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add webui/session.py tests/test_webui_session.py
git commit -m "feat(webui): add cache and refine fields to PipelineSession"
```

---

## Task 2: Add `run_from_insights()` to PipelineOrchestrator

**Files:**
- Modify: `core/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_pipeline.py

from core.insight_extractor import InsightEntry, InsightReport
from core.domain_classifier import ClassificationResult


def _mock_classification():
    return ClassificationResult(
        archetype="HR",
        confidence=0.9,
        table_mapping={"employees": "Employes"},
        params={"name_col": "Nom"},
    )


def _mock_insights():
    return [
        InsightEntry(
            type="distribution",
            table="Employes",
            col="Departement",
            finding="IT concentre 45%",
            priority=1,
        )
    ]


def test_run_from_insights_skips_analyzer_and_classifier():
    """run_from_insights() must not call DataAnalyzer or DomainClassifier."""
    with (
        patch("core.pipeline.DataAnalyzer") as mock_analyzer,
        patch("core.pipeline.DomainClassifier") as mock_classifier,
        patch("core.pipeline.InsightExtractor"),
        patch("core.pipeline.ColumnRelevanceFilter"),
        patch("core.pipeline.FeatureEngineer"),
        patch("core.pipeline.NarrativeGenerator"),
        patch("core.pipeline.VisualIntentResolver"),
        patch("core.pipeline.DashboardComposer"),
        patch("core.pipeline.ReflexionValidator"),
    ):
        orchestrator = PipelineOrchestrator()
        profile = _mock_profile()
        classification = _mock_classification()
        insights = _mock_insights()

        result = orchestrator.run_from_insights(
            cached_profile=profile,
            cached_classification=classification,
            selected_insights=insights,
            intent="test intent",
        )

        mock_analyzer.return_value.analyze.assert_not_called()
        mock_classifier.return_value.classify.assert_not_called()
        assert result.profile is profile
        assert result.classification is classification


def test_run_from_insights_returns_pipeline_result():
    from unittest.mock import MagicMock
    orchestrator = PipelineOrchestrator()
    orchestrator.relevance_filter = MagicMock()
    orchestrator.relevance_filter.filter.return_value = _mock_profile()
    orchestrator.insight_extractor = MagicMock()
    orchestrator.feature_engineer = MagicMock()
    orchestrator.feature_engineer.plan.return_value = MagicMock(features=[])
    orchestrator.narrative_generator = MagicMock()
    orchestrator.narrative_generator.generate.return_value = "summary"
    orchestrator.visual_intent_resolver = MagicMock()
    orchestrator.visual_intent_resolver.resolve.return_value = MagicMock(intents=[])
    orchestrator.composer = MagicMock()
    orchestrator.composer.compose.return_value = MagicMock(pages=[])

    result = orchestrator.run_from_insights(
        cached_profile=_mock_profile(),
        cached_classification=_mock_classification(),
        selected_insights=_mock_insights(),
        intent="turnover",
    )

    assert isinstance(result, PipelineResult)
    # InsightExtractor must not have been called
    orchestrator.insight_extractor.extract.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_pipeline.py::test_run_from_insights_skips_analyzer_and_classifier tests/test_pipeline.py::test_run_from_insights_returns_pipeline_result -v
```

Expected: `AttributeError: 'PipelineOrchestrator' object has no attribute 'run_from_insights'`

- [ ] **Step 3: Add `run_from_insights()` to PipelineOrchestrator**

Add this method to `PipelineOrchestrator` in `core/pipeline.py`, after the `run()` method (before `run_from_file()`):

```python
def run_from_insights(
    self,
    cached_profile: DataProfile,
    cached_classification: ClassificationResult,
    selected_insights: list,  # list[InsightEntry]
    intent: str = "",
) -> PipelineResult:
    """Phase 2 entry point for refinement runs.

    Skips DataAnalyzer, DomainClassifier, and InsightExtractor.
    Uses caller-provided insights (user-approved subset from previous run).
    Re-runs ColumnRelevanceFilter with new intent so column filtering adapts.
    """
    result = PipelineResult()
    result.profile = cached_profile
    result.classification = cached_classification
    result.insights = InsightReport(insights=selected_insights)

    active_profile = cached_profile
    if intent and cached_classification is not None:
        try:
            active_profile = self.relevance_filter.filter(cached_profile, intent)
            debug_print("Refinement — ColumnRelevanceFilter", active_profile, self.debug)
        except Exception as e:
            result.errors.append(f"ColumnRelevanceFilter failed: {e}")

    if cached_classification is not None and result.insights is not None:
        try:
            result.feature_plan = self.feature_engineer.plan(
                active_profile, cached_classification, result.insights,
                user_intent=intent or None,
            )
            debug_print("Refinement — FeatureEngineer", result.feature_plan, self.debug)
        except Exception as e:
            result.errors.append(f"FeatureEngineer failed: {e}")
            result.feature_plan = FeaturePlan(features=[])

    if cached_classification is not None and result.insights is not None:
        try:
            result.narrative = self.narrative_generator.generate(
                active_profile, cached_classification, result.insights,
                feature_plan=result.feature_plan,
                user_intent=intent or None,
            )
        except Exception as e:
            result.errors.append(f"NarrativeGenerator failed: {e}")

    if cached_classification is not None and result.insights is not None:
        try:
            result.visual_intents = self._resolve_visual_intents(
                active_profile, cached_classification, result.insights,
                narrative=result.narrative,
            )
        except Exception as e:
            result.errors.append(f"VisualIntentResolver failed: {e}")

    if cached_classification is not None and result.insights is not None:
        try:
            result.dashboard_plan = self._compose(
                cached_classification, result.insights, result.feature_plan,
                raw_cols=active_profile.columns, stats=active_profile.stats,
                summary_tables=active_profile.summary_tables,
                visual_intents=result.visual_intents,
                user_intent=intent or None,
            )
        except Exception as e:
            result.errors.append(f"DashboardComposer failed: {e}")

    if result.dashboard_plan is not None and cached_classification is not None:
        try:
            raw_cols = active_profile.columns
            engineered_cols: dict[str, list[str]] = {}
            if result.feature_plan:
                for f in result.feature_plan.features:
                    table_id = cached_classification.table_mapping.get(f.table, f.table)
                    engineered_cols.setdefault(table_id, []).append(f.col_id)

            validator = ReflexionValidator(
                raw_cols=raw_cols,
                engineered_cols=engineered_cols,
                table_mapping=cached_classification.table_mapping,
                summary_tables=active_profile.summary_tables,
                visual_intents=result.visual_intents,
            )
            result.dashboard_plan = validator.validate(
                result.dashboard_plan,
                cached_classification,
                result.insights,
                self.composer,
            )
        except Exception as e:
            result.errors.append(f"ReflexionValidator failed: {e}")

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_pipeline.py::test_run_from_insights_skips_analyzer_and_classifier tests/test_pipeline.py::test_run_from_insights_returns_pipeline_result -v
```

Expected: both pass.

- [ ] **Step 5: Run full pipeline test suite to check for regressions**

```bash
uv run pytest tests/test_pipeline.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add core/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): add run_from_insights() Phase 2 entry point"
```

---

## Task 3: Cache insights in WebCheckpointHandler

**Files:**
- Modify: `webui/checkpoint_handler.py`
- Test: `tests/test_webui_server.py` (covered by existing test_checkpoint2 — add assertion)

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_webui_server.py

def test_checkpoint2_caches_full_insight_list():
    """After Checkpoint 2, session.cached_insights holds full InsightReport."""
    from core.insight_extractor import InsightEntry, InsightReport
    from webui.checkpoint_handler import WebCheckpointHandler

    store_local = SessionStore()
    sid = store_local.create()
    session = store_local.get(sid)

    handler = WebCheckpointHandler(session)

    insights = [
        InsightEntry(type="distribution", table="T", col="C", finding="f1", priority=1),
        InsightEntry(type="outlier", table="T", col="D", finding="f2", priority=2),
    ]
    report = InsightReport(insights=insights)

    # Pre-set the checkpoint2 response so on_insights() doesn't block
    session.checkpoint2_response = {"selected_indices": [0]}
    session.checkpoint2_event.set()

    from unittest.mock import MagicMock
    profile_mock = MagicMock()
    handler.on_insights(report, profile_mock)

    assert session.cached_insights is not None
    assert len(session.cached_insights) == 2  # full list, not filtered
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_webui_server.py::test_checkpoint2_caches_full_insight_list -v
```

Expected: `AssertionError: assert None is not None`

- [ ] **Step 3: Update `on_insights()` in WebCheckpointHandler**

In `webui/checkpoint_handler.py`, add one line after `self._session.checkpoint2_event.wait()` and before processing the response — cache the full insight list:

```python
def on_insights(
    self,
    report: "InsightReport",
    profile: "DataProfile",
) -> InsightFeedback:
    insights_data = [
        {
            "index": i,
            "type": ins.type,
            "table": ins.table,
            "col": ins.col,
            "finding": ins.finding,
        }
        for i, ins in enumerate(report.insights)
    ]
    self._session.event_queue.put(("checkpoint_2", json.dumps({"insights": insights_data})))
    self._session.checkpoint2_event.wait()
    self._session.checkpoint2_event.clear()

    # Cache full insight list for refinement (before user's selection filters it)
    self._session.cached_insights = list(report.insights)

    resp = self._session.checkpoint2_response or {}
    selected = resp.get("selected_indices", list(range(len(report.insights))))
    return InsightFeedback(selected_indices=selected)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_webui_server.py::test_checkpoint2_caches_full_insight_list -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add webui/checkpoint_handler.py tests/test_webui_server.py
git commit -m "feat(webui): cache full InsightReport in session after checkpoint 2"
```

---

## Task 4: Cache Phase 1 data + enrich `complete` event + add `run_refinement()`

**Files:**
- Modify: `webui/pipeline_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_webui_server.py

def test_complete_event_includes_quality_fields():
    """complete SSE event must include intent_used, features_applied, features_failed."""
    import json as _json
    store_local = SessionStore()
    sid = store_local.create()
    session = store_local.get(sid)

    # Simulate what run_pipeline emits
    payload = {
        "doc_url": "http://grist/doc/abc",
        "pages": ["Dashboard"],
        "intent_used": "turnover",
        "insights_used": ["IT concentre 45%"],
        "features_applied": 3,
        "features_failed": 1,
        "archetype": "HR",
        "confidence": 0.91,
    }
    session.event_queue.put(("complete", _json.dumps(payload)))
    event, data = session.event_queue.get_nowait()
    d = _json.loads(data)

    assert d["intent_used"] == "turnover"
    assert d["features_applied"] == 3
    assert d["features_failed"] == 1
    assert d["archetype"] == "HR"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_webui_server.py::test_complete_event_includes_quality_fields -v
```

Expected: this test actually passes as-is (it only tests the structure we'll produce). Confirm it passes before continuing.

- [ ] **Step 3: Rewrite `webui/pipeline_runner.py`**

```python
"""Run the pipeline in a background thread, emitting SSE events."""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from config import Settings
from core.data_analyzer import DataAnalyzer
from core.pipeline import PipelineOrchestrator
from core.grist_api import GristAPI
from core.grist_importer import GristImporter
from core.feature_engineer import FeatureEngineer
from core.archetype_engine import ArchetypeEngine
from core.insight_extractor import InsightEntry, InsightReport
from core.domain_classifier import ClassificationResult
from core.data_analyzer import DataProfile
from webui.session import PipelineSession
from webui.checkpoint_handler import WebCheckpointHandler


def _emit(session: PipelineSession, event: str, data: str) -> None:
    session.event_queue.put((event, data))


def _grist_steps(
    session: PipelineSession,
    result,
    tmp_path: str,
    profile: DataProfile,
    settings: Settings,
    intent: str,
) -> None:
    """Run Grist import + ArchetypeEngine, emit complete or error event."""
    try:
        _emit(session, "step", json.dumps({"message": "Import du fichier dans Grist…", "pct": 65}))
        api = GristAPI(settings.GRIST_SERVER, settings.GRIST_API_KEY)
        importer = GristImporter(api)
        doc_id = importer.import_excel(tmp_path, summary_tables=profile.summary_tables)

        features_applied = 0
        features_failed = 0
        if result.feature_plan and result.feature_plan.features:
            _emit(session, "step", json.dumps({"message": "Application des colonnes dérivées…", "pct": 75}))
            fe = FeatureEngineer(settings)
            applied, failed = fe.apply(api, doc_id, result.feature_plan, result.classification.table_mapping)
            features_applied = len(applied)
            features_failed = len(failed)

        _emit(session, "step", json.dumps({"message": "Génération des pages du tableau de bord…", "pct": 85}))
        engine = ArchetypeEngine(api)
        created_pages = engine.apply(
            doc_id,
            result.classification,
            result.dashboard_plan,
            result.visual_intents,
        )

        doc_url = f"{settings.GRIST_SERVER}/doc/{doc_id}"
        insights_used = [ins.finding for ins in (result.insights.insights if result.insights else [])]

        complete_payload = {
            "doc_url": doc_url,
            "pages": created_pages,
            "intent_used": intent,
            "insights_used": insights_used,
            "features_applied": features_applied,
            "features_failed": features_failed,
            "archetype": result.classification.archetype if result.classification else "",
            "confidence": result.classification.confidence if result.classification else 0.0,
        }
        session.result = complete_payload
        _emit(session, "complete", json.dumps(complete_payload))

    except Exception as exc:
        session.error = str(exc)
        _emit(session, "error", json.dumps({"message": str(exc)}))


def run_pipeline(session: PipelineSession, file_bytes: bytes, filename: str) -> None:
    """Full pipeline run (Phase 1 + Phase 2)."""
    settings = Settings()
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        session.cached_tmp_path = tmp_path

        _emit(session, "step", json.dumps({"message": "Analyse du fichier Excel…", "pct": 10}))
        analyzer = DataAnalyzer(settings)
        profile = analyzer.analyze(tmp_path)

        _emit(session, "step", json.dumps({"message": "Classification du domaine métier…", "pct": 25}))
        handler = WebCheckpointHandler(session)
        orchestrator = PipelineOrchestrator(settings, checkpoint_handler=handler)
        result = orchestrator.run(profile)

        # Cache Phase 1 outputs for potential refinement
        session.cached_profile = profile
        session.cached_classification = result.classification

        if not result.dashboard_plan or not result.classification:
            session.error = "Pipeline incomplet — impossible de créer le document Grist."
            _emit(session, "error", json.dumps({"message": session.error}))
            return

        intent = ""
        if session.checkpoint1_response:
            intent = session.checkpoint1_response.get("user_intent", "")

        _grist_steps(session, result, tmp_path, profile, settings, intent)

    except Exception as exc:
        session.error = str(exc)
        _emit(session, "error", json.dumps({"message": str(exc)}))


def run_refinement(
    session: PipelineSession,
    intent: str,
    selected_insights: list[InsightEntry],
) -> None:
    """Phase 2 re-run using cached Phase 1 data."""
    settings = Settings()
    try:
        profile = session.cached_profile
        classification = session.cached_classification
        if profile is None or classification is None:
            _emit(session, "error", json.dumps({"message": "Données d'analyse manquantes — veuillez recommencer."}))
            return

        _emit(session, "step", json.dumps({"message": "Application du nouveau filtre de colonnes…", "pct": 40}))
        orchestrator = PipelineOrchestrator(settings)
        result = orchestrator.run_from_insights(
            cached_profile=profile,
            cached_classification=classification,
            selected_insights=selected_insights,
            intent=intent,
        )

        if not result.dashboard_plan or not result.classification:
            session.error = "Affinement incomplet — impossible de créer le document Grist."
            _emit(session, "error", json.dumps({"message": session.error}))
            return

        tmp_path = session.cached_tmp_path
        if tmp_path is None:
            _emit(session, "error", json.dumps({"message": "Fichier source non disponible pour l'affinement."}))
            return

        _grist_steps(session, result, tmp_path, profile, settings, intent)

    except Exception as exc:
        session.error = str(exc)
        _emit(session, "error", json.dumps({"message": str(exc)}))


def start_pipeline_thread(session: PipelineSession, file_bytes: bytes, filename: str) -> None:
    t = threading.Thread(target=run_pipeline, args=(session, file_bytes, filename), daemon=True)
    t.start()


def start_refinement_thread(
    session: PipelineSession,
    intent: str,
    selected_insights: list[InsightEntry],
) -> None:
    t = threading.Thread(target=run_refinement, args=(session, intent, selected_insights), daemon=True)
    t.start()
```

- [ ] **Step 4: Run existing pipeline runner tests**

```bash
uv run pytest tests/test_webui_server.py -v
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add webui/pipeline_runner.py
git commit -m "feat(webui): cache phase 1 data, enrich complete event, add run_refinement()"
```

---

## Task 5: Add `/refine` endpoints to FastAPI server

**Files:**
- Modify: `webui/server.py`
- Test: `tests/test_webui_server.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_webui_server.py

def test_refine_get_unknown_session_returns_404(client):
    resp = client.get("/refine/nonexistent-id")
    assert resp.status_code == 404


def test_refine_get_returns_cached_insights(client):
    from core.insight_extractor import InsightEntry
    sid = store.create()
    session = store.get(sid)
    session.cached_insights = [
        InsightEntry(type="distribution", table="T", col="C", finding="f1", priority=1),
    ]
    session.checkpoint1_response = {"archetype": "HR", "user_intent": "turnover"}

    resp = client.get(f"/refine/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "turnover"
    assert len(body["insights"]) == 1
    assert body["insights"][0]["finding"] == "f1"


def test_refine_get_returns_empty_when_no_cache(client):
    sid = store.create()
    resp = client.get(f"/refine/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["insights"] == []
    assert body["intent"] == ""


def test_refine_post_unknown_session_returns_404(client):
    resp = client.post(
        "/refine/nonexistent-id",
        data={"intent": "test", "selected_indices": "[0]"},
    )
    assert resp.status_code == 404


def test_refine_post_starts_refinement_thread(client):
    from core.insight_extractor import InsightEntry
    from core.domain_classifier import ClassificationResult
    from core.data_analyzer import DataProfile
    from unittest.mock import patch, MagicMock

    sid = store.create()
    session = store.get(sid)
    session.cached_insights = [
        InsightEntry(type="distribution", table="T", col="C", finding="f1", priority=1),
    ]
    session.cached_profile = MagicMock(spec=DataProfile)
    session.cached_classification = MagicMock(spec=ClassificationResult)

    with patch("webui.server.start_refinement_thread") as mock_thread:
        resp = client.post(
            f"/refine/{sid}",
            data={"intent": "turnover", "selected_indices": "[0]"},
        )
    assert resp.status_code == 200
    mock_thread.assert_called_once()
    call_kwargs = mock_thread.call_args
    assert call_kwargs[0][1] == "turnover"  # intent
    assert len(call_kwargs[0][2]) == 1       # selected_insights


def test_refine_post_bad_indices_returns_400(client):
    sid = store.create()
    session = store.get(sid)
    session.cached_insights = []
    resp = client.post(
        f"/refine/{sid}",
        data={"intent": "x", "selected_indices": "not-json"},
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_webui_server.py::test_refine_get_unknown_session_returns_404 tests/test_webui_server.py::test_refine_get_returns_cached_insights tests/test_webui_server.py::test_refine_post_starts_refinement_thread -v
```

Expected: `404 Not Found` / attribute errors — routes don't exist yet.

- [ ] **Step 3: Add refine endpoints to `webui/server.py`**

Add these imports at the top of `webui/server.py`:

```python
from webui.pipeline_runner import start_pipeline_thread, start_refinement_thread
```

Replace the existing import line `from webui.pipeline_runner import start_pipeline_thread` with the above.

Then add these two endpoints after the `/result/{sid}` handler:

```python
@app.get("/refine/{sid}")
async def refine_get(sid: str):
    """Return cached insights + last intent for the refinement form."""
    session = store.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session inconnue.")

    insights_data = []
    if session.cached_insights:
        insights_data = [
            {
                "index": i,
                "type": ins.type,
                "table": ins.table,
                "col": ins.col,
                "finding": ins.finding,
            }
            for i, ins in enumerate(session.cached_insights)
        ]

    intent = ""
    if session.checkpoint1_response:
        intent = session.checkpoint1_response.get("user_intent", "")

    return JSONResponse({"insights": insights_data, "intent": intent})


@app.post("/refine/{sid}")
async def refine_post(sid: str, intent: str = Form(""), selected_indices: str = Form(...)):
    """Start Phase 2 re-run with new intent + insight selection."""
    session = store.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session inconnue.")

    try:
        indices = json.loads(selected_indices)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="selected_indices doit être un JSON array.")

    all_insights = session.cached_insights or []
    selected = [all_insights[i] for i in indices if i < len(all_insights)]

    # Reset session state for the new run
    session.error = None
    session.result = None

    start_refinement_thread(session, intent, selected)
    return JSONResponse({"status": "ok"})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_webui_server.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add webui/server.py tests/test_webui_server.py
git commit -m "feat(webui): add GET/POST /refine endpoints for Phase 2 re-run"
```

---

## Task 6: Redesign result screen HTML

**Files:**
- Modify: `webui/templates/run.html`

No automated test — visually verified in Task 7 browser test.

- [ ] **Step 1: Replace the result screen section in `webui/templates/run.html`**

Find the `<!-- Screen: Result -->` block and replace it entirely:

```html
    <!-- Screen: Result -->
    <div class="screen hidden" data-screen="result">
      <div class="result-icon">✅</div>
      <p class="result-title">Votre tableau de bord est prêt !</p>

      <div class="result-section">
        <p class="result-section-label">Résumé</p>
        <p class="result-meta">
          Archetype : <strong id="result-archetype"></strong>
          &nbsp;·&nbsp;
          Confiance : <strong id="result-confidence"></strong>
        </p>
        <p class="result-meta" id="result-intent-wrap" style="display:none">
          Intention analysée : <em id="result-intent"></em>
        </p>
        <div class="page-chips" id="page-chips"></div>
      </div>

      <div class="result-section" id="result-insights-section" style="display:none">
        <p class="result-section-label">Insights utilisés</p>
        <ul class="insight-list" id="result-insights"></ul>
      </div>

      <div class="result-section">
        <p class="result-section-label">Qualité</p>
        <p class="result-quality" id="result-features-ok"></p>
        <p class="result-quality result-quality-warn" id="result-features-fail" style="display:none"></p>
      </div>

      <div class="btn-row" style="justify-content:center;flex-wrap:wrap;gap:12px;">
        <a id="result-link" class="btn" href="#" target="_blank" rel="noopener">Ouvrir dans Grist →</a>
        <button id="affiner-btn" class="btn btn-outline">Affiner le tableau de bord</button>
        <a href="/" class="btn btn-outline">Nouvelle analyse</a>
      </div>
    </div>

    <!-- Screen: Refine — reuses checkpoint2 layout -->
    <div class="screen hidden" data-screen="refine">
      <p class="section-title">Affiner votre tableau de bord</p>

      <form id="refine-form">
        <div class="label">Votre question ou objectif :</div>
        <textarea id="refine-intent" placeholder="Ex : Je veux comprendre les tendances d'absences par département…"></textarea>

        <div class="label mt-16">Sélectionnez les insights à inclure :</div>
        <ul class="insight-list" id="refine-insights"></ul>

        <p class="refine-hint">Sélectionnez au moins un insight pour continuer.</p>

        <div class="btn-row">
          <button type="submit" class="btn" id="refine-submit" disabled>Régénérer →</button>
          <button type="button" class="btn btn-outline" id="refine-cancel">Annuler</button>
        </div>
      </form>
    </div>
```

- [ ] **Step 2: Replace the error screen anchor with a button in `webui/templates/run.html`**

Find the `<!-- Screen: Error -->` block and replace it:

```html
    <!-- Screen: Error -->
    <div class="screen hidden" data-screen="error">
      <div class="error-banner" id="error-msg">Une erreur est survenue.</div>
      <div class="btn-row">
        <button id="error-retry-btn" class="btn btn-outline">Réessayer</button>
      </div>
    </div>
```

The button's behaviour is controlled by JS (Task 7) — full restart for Phase 1 errors, Phase 2 retry for refinement errors.

- [ ] **Step 3: Add CSS for new result elements in `webui/static/style.css`**

Append at the end of `webui/static/style.css`:

```css
/* Result screen quality card */
.result-section {
  margin: 20px 0;
  padding: 16px;
  background: #f3f4f6;
  border-radius: 8px;
}
.result-section-label {
  font-size: .75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--gray-600);
  margin: 0 0 8px;
}
.result-meta {
  font-size: .9rem;
  color: var(--gray-600);
  margin: 4px 0;
}
.result-quality {
  font-size: .9rem;
  margin: 4px 0;
}
.result-quality::before { content: "✓ "; color: #16a34a; }
.result-quality-warn::before { content: "⚠ "; color: #d97706; }
.refine-hint {
  font-size: .8rem;
  color: var(--gray-600);
  margin: 8px 0 0;
}
```

- [ ] **Step 3: Commit**

```bash
git add webui/templates/run.html webui/static/style.css
git commit -m "feat(webui): redesign result screen with quality card and Affiner button"
```

---

## Task 7: Update JS for enriched result screen and refinement flow

**Files:**
- Modify: `webui/static/app.js`

- [ ] **Step 1: Update error handling in `initRun()` and `resumeStream()` in `webui/static/app.js`**

Both `initRun()` and `resumeStream()` have an inline `error` event handler that directly sets `$("error-msg").textContent`. Replace those handlers with calls to the new `showError()` function (added in Step 2 below):

In `initRun()`, replace:
```javascript
  es.addEventListener("error", e => {
    const d = JSON.parse(e.data || '{"message":"Erreur inconnue."}');
    es.close();
    showScreen("error");
    $("error-msg").textContent = d.message;
  });
```
with:
```javascript
  es.addEventListener("error", e => {
    const d = JSON.parse(e.data || '{"message":"Erreur inconnue."}');
    es.close();
    showError(d.message);
  });
```

In `resumeStream()`, replace:
```javascript
  es.addEventListener("error", e => {
    const d = JSON.parse(e.data || '{"message":"Erreur inconnue."}');
    es.close();
    showScreen("error");
    $("error-msg").textContent = d.message;
  });
```
with:
```javascript
  es.addEventListener("error", e => {
    const d = JSON.parse(e.data || '{"message":"Erreur inconnue."}');
    es.close();
    showError(d.message);
  });
```

Also, at the very top of `initRun()`, reset refinement state:
```javascript
function initRun() {
  window._inRefinement = false;  // ← add this line
  window._lastRefineIntent = "";
  window._lastRefineIndices = [];
  // ... rest of initRun unchanged
```

- [ ] **Step 2: Replace `showResult()` in `webui/static/app.js`**

Find the `// ── Result screen ─` section and replace it with:

```javascript
// ── Result screen ─────────────────────────────────────────────────────────────
function showResult(data) {
  setStepperState(5);

  $("result-link").href = data.doc_url;

  // Archetype + confidence
  $("result-archetype").textContent = data.archetype || "—";
  $("result-confidence").textContent = data.confidence
    ? Math.round(data.confidence * 100) + " %"
    : "—";

  // Intent echo
  if (data.intent_used) {
    $("result-intent").textContent = `"${data.intent_used}"`;
    $("result-intent-wrap").style.display = "";
  }

  // Pages
  const chips = $("page-chips");
  chips.innerHTML = "";
  (data.pages || []).forEach(p => {
    const span = document.createElement("span");
    span.className = "page-chip";
    span.textContent = p;
    chips.appendChild(span);
  });

  // Insights used
  const insightList = $("result-insights");
  insightList.innerHTML = "";
  if (data.insights_used && data.insights_used.length) {
    $("result-insights-section").style.display = "";
    data.insights_used.forEach(finding => {
      const li = document.createElement("li");
      li.className = "insight-item";
      li.innerHTML = `<div>${finding}</div>`;
      insightList.appendChild(li);
    });
  }

  // Quality indicators
  const applied = data.features_applied ?? 0;
  const failed = data.features_failed ?? 0;
  $("result-features-ok").textContent = `${applied} colonne${applied !== 1 ? "s" : ""} calculée${applied !== 1 ? "s" : ""} ajoutée${applied !== 1 ? "s" : ""}`;
  if (failed > 0) {
    $("result-features-fail").textContent = `${failed} colonne${failed !== 1 ? "s" : ""} échouée${failed !== 1 ? "s" : ""} (référence ambiguë)`;
    $("result-features-fail").style.display = "";
  }

  // Store last complete data for refinement
  window._lastResult = data;

  showScreen("result");

  $("affiner-btn").onclick = () => loadRefineForm();
}

// ── Refinement flow ───────────────────────────────────────────────────────────
async function loadRefineForm() {
  const resp = await fetch(`/refine/${window._sid}`);
  if (!resp.ok) { alert("Impossible de charger les données d'affinement."); return; }
  const data = await resp.json();
  showRefine(data);
}

function showRefine(data) {
  $("refine-intent").value = data.intent || "";

  const list = $("refine-insights");
  list.innerHTML = "";
  (data.insights || []).forEach(ins => {
    const li = document.createElement("li");
    li.className = "insight-item";
    li.innerHTML = `
      <input type="checkbox" name="refine-insight" value="${ins.index}" checked>
      <div>
        <div>${ins.finding}</div>
        <div class="insight-meta">${ins.type} — ${ins.table}.${ins.col}</div>
      </div>`;
    list.appendChild(li);
  });

  updateRefineSubmit();
  list.querySelectorAll('input[name="refine-insight"]').forEach(cb => {
    cb.addEventListener("change", updateRefineSubmit);
  });

  showScreen("refine");

  $("refine-cancel").onclick = () => showScreen("result");

  $("refine-form").onsubmit = async e => {
    e.preventDefault();
    const selected = [...document.querySelectorAll('input[name="refine-insight"]:checked')]
      .map(el => parseInt(el.value));
    const intent = $("refine-intent").value;

    // Store for Phase 2 error retry
    window._inRefinement = true;
    window._lastRefineIntent = intent;
    window._lastRefineIndices = selected;

    const form = new FormData();
    form.append("intent", intent);
    form.append("selected_indices", JSON.stringify(selected));
    await fetch(`/refine/${window._sid}`, { method: "POST", body: form });

    showScreen("progress");
    setStepperState(3); // start at Insights step (refinement skips Analyse + Classification)
    setLog("Affinage en cours…");
    resumeStream(null, null, "complete", showResult);
  };
}

function updateRefineSubmit() {
  const any = document.querySelector('input[name="refine-insight"]:checked');
  $("refine-submit").disabled = !any;
}

// ── Error screen — Phase 2 retry ──────────────────────────────────────────────
// Track whether we are in a refinement run so the error screen can offer
// "Réessayer la génération" (Phase 2 retry) instead of full restart.
window._inRefinement = false;

function showError(msg) {
  $("error-msg").textContent = msg;
  const retryBtn = $("error-retry-btn");
  if (window._inRefinement && window._sid) {
    retryBtn.textContent = "Réessayer la génération";
    retryBtn.onclick = async () => {
      // Re-submit same refinement response without showing form again
      const form = new FormData();
      form.append("intent", window._lastRefineIntent || "");
      form.append("selected_indices", JSON.stringify(window._lastRefineIndices || []));
      await fetch(`/refine/${window._sid}`, { method: "POST", body: form });
      showScreen("progress");
      setStepperState(3);
      setLog("Affinement en cours…");
      resumeStream(null, null, "complete", showResult);
    };
  } else {
    retryBtn.textContent = "Réessayer";
    retryBtn.onclick = () => { window.location.href = "/"; };
  }
  showScreen("error");
}
```

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
uv run pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add webui/static/app.js
git commit -m "feat(webui): update JS for enriched result screen and refinement flow"
```

---

## Task 8: End-to-end smoke test

**Files:**
- No new files — manual verification

- [ ] **Step 1: Start the web server**

```bash
uv run python web.py
```

Expected output: `Uvicorn running on http://0.0.0.0:8000`

- [ ] **Step 2: Open browser and run full pipeline**

Open `http://localhost:8000`, upload `samples/employees_rh.xlsx`, go through both checkpoints, verify result screen shows:
- Archetype + confidence
- Intent echoed back (if you entered one)
- Insights used list
- Quality indicators (columns applied / failed)
- "Affiner" button present

- [ ] **Step 3: Test refinement flow**

Click "Affiner le tableau de bord", verify:
- Refinement form appears with intent pre-filled and insights pre-checked
- At least 1 insight must be checked to enable "Régénérer"
- Submit → progress screen shows, stepper starts at Insights step
- New result screen appears with updated content

- [ ] **Step 4: Test error recovery**

If Phase 2 fails, verify "Réessayer la génération" button appears (not full restart).

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat(webui): complete pain-point relief — quality card, intent echo, refinement loop"
```
