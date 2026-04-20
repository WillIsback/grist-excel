# Pain-Point Relief Design — grist-excel

**Date:** 2026-04-20
**Status:** Approved
**Audience:** IT team implementing the refinement loop

---

## Problem

The assumed user pain-point: non-expert uploads Excel, receives a useful Grist dashboard — zero Grist knowledge required.

The web UI (FastAPI + SSE) removes the CLI barrier. But three gaps prevent full pain-point relief:

1. **No output validation loop** — pipeline quality is the #1 user friction. When output is poor, the only option is a full restart (re-upload + re-wait + re-do all checkpoints). Iteration cost is maximum.
2. **Intent effect is invisible** — user types a business question at Checkpoint 1; the result screen shows no indication that it was used or how it shaped the output.
3. **FeatureEngineer failures are silent** — derived formula columns fail HTTP 400 and the pipeline continues; users open Grist and discover empty columns with no explanation.

---

## Goal

Close all three gaps without adding happy-path friction:

- **Gap 1:** Add a cheap refinement loop (Phase 2 re-run using cached Phase 1 analysis).
- **Gap 2:** Echo intent + insights used on the result screen.
- **Gap 3:** Surface formula failure count as a quality indicator on the result screen.

---

## Architecture

### Phase Split

`PipelineOrchestrator.run()` splits into two phases:

```
Phase 1 — Analysis (heavy, runs once per upload):
  DataAnalyzer        → DataProfile
  DomainClassifier    → ClassificationResult
  ColumnRelevanceFilter
  → results cached in PipelineSession

Phase 2 — Generation (re-runnable with new intent/insights):
  InsightExtractor    → InsightReport
  FeatureEngineer     → FeaturePlan + apply()
  VisualIntentResolver
  DashboardComposer   → DashboardPlan
  ReflexionValidator
  GristImporter
  ArchetypeEngine
  → produces new Grist document
```

New entry point on `PipelineOrchestrator`:

```python
def run_from_insights(
    self,
    cached_profile: DataProfile,
    cached_classification: ClassificationResult,
    intent: str,
    selected_insights: list[Insight],  # user-approved subset of cached InsightReport
) -> PipelineResult:
    ...
```

Skips Agents 1, 2, and InsightExtractor. Reuses cached `DataProfile`, `ClassificationResult`, and the user-selected `Insight` objects directly as the InsightReport. Re-runs `ColumnRelevanceFilter` with the new intent (so column filtering adapts), then feeds selected insights into `FeatureEngineer` onward. Produces a new Grist document.

**Why skip InsightExtractor in refinement:** Re-running it with a new intent generates new insights that don't match what the user selected on the form. Passing user-selected insights directly is both cheaper and more predictable.

### Session Store

```python
@dataclass
class PipelineSession:
    # existing fields
    event_queue: queue.Queue
    checkpoint1_event: threading.Event
    checkpoint1_response: dict | None
    checkpoint2_event: threading.Event
    checkpoint2_response: dict | None
    result: dict | None
    error: str | None

    # new — populated after Phase 1, reused by refinement runs
    cached_profile: DataProfile | None = None
    cached_classification: ClassificationResult | None = None

    # new — populated after Checkpoint 2, reused as refinement source
    cached_insights: list[Insight] | None = None  # full InsightReport from last run

    # new — refinement checkpoint
    refine_event: threading.Event = field(default_factory=threading.Event)
    refine_response: dict | None = None  # {intent, selected_insight_indices: list[int]}
```

Session TTL resets to 30 minutes on each refinement run.

### HTTP Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/upload` | Receive `.xlsx`, start Phase 1+2 thread, return `{session_id}` — unchanged |
| `GET`  | `/stream/{id}` | SSE stream — unchanged, reused for refinement progress |
| `POST` | `/checkpoint1/{id}` | Submit archetype override + intent — unchanged |
| `POST` | `/checkpoint2/{id}` | Submit selected insight indices — unchanged |
| `GET`  | `/result/{id}` | Return final result — unchanged |
| `POST` | `/refine/{id}` | Submit new intent + insight selection; triggers Phase 2 re-run |

### SSE Event Vocabulary — Changes

**Extended `complete` event:**

```
event: complete
data: {
  "doc_url": "https://...",
  "pages": ["Dashboard RH", "Employés", "Saisie"],
  "intent_used": "pourquoi le turnover est élevé",
  "insights_used": ["IT concentre 45%...", "Pic absences janvier..."],
  "features_applied": 4,
  "features_failed": 1,
  "archetype": "HR",
  "confidence": 0.91
}
```

**New `refine_ready` event** — emitted immediately on POST `/refine/{id}` with empty body:

```
event: refine_ready
data: {
  "insights": [...],        ← cached_insights from last run (full list, pre-checked)
  "intent": "pourquoi le turnover est élevé",   ← intent from last run
  "archetype": "HR"
}
```

`selected_insight_indices` in the refinement form submission are indices into this cached list. Server resolves them to `Insight` objects before calling `run_from_insights`.

Frontend reconnects `EventSource` on refinement, replays `step` events, receives new `complete`.

---

## UI / UX

### Screen 5 — Result (redesigned)

```
✓ Votre tableau de bord est prêt

[ Ouvrir dans Grist ]                    ← primary CTA

─── Résumé ───────────────────────────────────
Archetype détecté : HR (91%)
Intention analysée : "pourquoi le turnover est élevé"
Pages créées : Dashboard RH · Employés · Saisie

─── Insights utilisés ────────────────────────
• IT concentre 45% des effectifs
• Pic d'absences en janvier (+40%)
• 8 salaires > 80k€ en IT senior

─── Qualité ──────────────────────────────────
✓ 4 colonnes calculées ajoutées
⚠ 1 colonne échouée (référence ambiguë)

[ Affiner le tableau de bord ]           ← secondary CTA
[ Nouvelle analyse ]                     ← tertiary CTA
```

### Refinement Flow (reuses Screen 4 layout)

1. User clicks "Affiner le tableau de bord"
2. JS reconnects `EventSource /stream/{id}`
3. POST `/refine/{id}` with empty body → server emits `refine_ready`
4. Frontend shows pre-populated form (Screen 4 layout):
   - Textarea: intent (pre-filled, editable)
   - Checklist: all insights (pre-checked as in previous run, reselectable)
   - "Régénérer" button
5. User submits → POST `/refine/{id}` with `{intent, selected_indices}`
6. SSE `step` events stream Phase 2 progress (stepper shows "Insights · Génération" only — Analyse + Classification greyed out)
7. New `complete` event → new Screen 5

### Screen 2 — Progression (refinement mode)

Stepper label changes to "Affinage en cours...". Steps "Analyse" and "Classification" are greyed out; stepper starts at "Insights".

---

## Error Handling

| Situation | Behavior |
|-----------|----------|
| Phase 1 fails | `error` SSE → red banner + "Réessayer" (full restart — no cache yet) |
| Phase 2 fails | `error` SSE → red banner + "Réessayer la génération" button — triggers Phase 2 re-run with cached Phase 1, no form shown |
| FeatureEngineer partial failure | Pipeline continues; `features_failed` count in `complete` → ⚠ on Screen 5 |
| No insights selected on refinement | Client-side: "Régénérer" disabled until at least 1 insight checked |
| Session expired during refinement | `/refine/{id}` returns 404 → JS shows "Session expirée — veuillez recommencer" + "Nouvelle analyse" |
| Grist importer fails | `error` SSE → "Réessayer la génération" (Phase 2 retry with cached inputs) |

**Key principle:** Phase 1 failure = full restart. Phase 2 failure = cheap retry using cached Phase 1 data.

---

## Pain-Point Relief Mapping

| Gap | Fixed by |
|-----|----------|
| No output validation loop | Phase split + `/refine` endpoint + "Affiner" button on Screen 5 |
| Intent effect invisible | `intent_used` + `insights_used` in `complete` event → displayed on Screen 5 |
| Silent FeatureEngineer failures | `features_applied` + `features_failed` in `complete` event → ⚠ on Screen 5 |

---

## Out of Scope

- Authentication / multi-user isolation (v1 constraint unchanged)
- Persistent session storage — refinement reuses in-memory cache only
- Partial chart editing (accept/reject individual charts before Grist creation)
- Mobile-responsive layout
- Dark mode
- Progress cancellation
