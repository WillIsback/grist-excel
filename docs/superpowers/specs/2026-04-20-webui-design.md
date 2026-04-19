# Web UI Design — grist-excel

**Date:** 2026-04-20  
**Status:** Approved  
**Audience:** Non-technical business users (utilisateurs métier)

---

## Problem

The CLI pipeline is powerful but inaccessible to non-technical users. Business users need to upload an Excel file and receive a Grist dashboard — without touching a terminal. The interactive checkpoint mode (archetype selection, insight validation) is essential to product value and must surface in the UI.

---

## Goal

A lightweight, self-hosted web UI that:
- Accepts an Excel file upload
- Streams real-time pipeline progression to the user
- Pauses at two interactive checkpoints for user confirmation/correction
- Delivers the finished Grist document URL

---

## Architecture

**Stack:** FastAPI (Python) + vanilla JS + Server-Sent Events (SSE). No JS framework, no build step, no extra runtime.

```
webui/
├── server.py           # FastAPI app: routes, SSE streaming, checkpoint endpoints
├── pipeline_runner.py  # Runs pipeline in background thread, emits SSE events
├── session.py          # In-memory session store: uuid → {thread, events queue, pause Events}
static/
├── style.css
└── app.js
templates/
├── index.html          # Upload screen
└── run.html            # Progression + checkpoint screens (single-page, JS-driven)
```

### HTTP Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/upload` | Receive `.xlsx`, start pipeline thread, return `{session_id}` |
| `GET`  | `/stream/{id}` | SSE stream — emits `step`, `checkpoint_1`, `checkpoint_2`, `complete`, `error` |
| `POST` | `/checkpoint1/{id}` | Submit archetype override + user intent; resume pipeline |
| `POST` | `/checkpoint2/{id}` | Submit selected insight indices; resume pipeline |
| `GET`  | `/result/{id}` | Return final Grist doc URL |

### SSE Event Vocabulary

```
event: step
data: {"message": "Analyse des données...", "pct": 20}

event: checkpoint_1
data: {"archetype": "HR", "confidence": 0.91, "intents": [...]}

event: checkpoint_2
data: {"insights": [...]}

event: complete
data: {"doc_url": "https://...", "pages": ["Dashboard RH", "Employés"]}

event: error
data: {"message": "..."}
```

### Checkpoint Blocking Mechanism

The pipeline runs in a `threading.Thread`. At each checkpoint, it calls `checkpoint_handler.on_checkpoint()`, which blocks on a `threading.Event`. The SSE stream sends the checkpoint event to the frontend. When the user submits the checkpoint form, the corresponding `POST /checkpoint{N}/{id}` endpoint stores the user's response in the session and calls `event.set()`, unblocking the pipeline thread.

```
Pipeline thread           Session store              Frontend (JS)
─────────────            ─────────────              ─────────────
run() …                  event_queue: []            EventSource /stream/id
  → emit step(20%)  →→→  [step(20%)]           →→→  update stepper
  → checkpoint_1    →→→  [checkpoint_1(data)]   →→→  show form
  → block on Ev1
                         POST /checkpoint1/id
                         store response
                         ev1.set()          ←←←  user submits form
  ← unblocked
  → emit step(60%)  →→→  [step(60%)]           →→→  update stepper
  → checkpoint_2    →→→  [checkpoint_2(data)]   →→→  show insight list
  → block on Ev2
                         POST /checkpoint2/id
                         ev2.set()          ←←←  user submits
  ← unblocked
  → complete        →→→  [complete(url)]       →→→  show result
```

---

## UI / UX

### Style

- **Font:** `system-ui, -apple-system, sans-serif`
- **Accent:** `#16A34A` (Grist green)
- **Layout:** 680px centered, white card on `#F9FAFB` background
- **No external CDN dependencies** — all assets served locally

### Screens (single HTML page, JS-driven transitions)

**Screen 1 — Upload**
- Logo + tagline: "Transformez votre Excel en tableau de bord Grist"
- Drag-and-drop zone (also click-to-browse)
- File name preview on select
- "Analyser" button → POST /upload → transition to Screen 2

**Screen 2 — Progression**
- Horizontal stepper: Analyse · Classification · Checkpoint · Insights · Génération
- Live log line: current step description (updated via SSE `step` events)
- Animated progress bar (percentage from SSE)
- Transitions to Screen 3 on `checkpoint_1` event, Screen 4 on `checkpoint_2` event, Screen 5 on `complete`

**Screen 3 — Checkpoint 1: Archetype & Intent**
- Detected archetype badge + confidence %
- Radio group: confirm detected archetype or choose alternative (HR / Décisionnel / Support / Étudiant / SI / Projet / Générique)
- Textarea: "Votre question ou objectif (optionnel)"
- "Continuer l'analyse" → POST /checkpoint1/{id} → back to Screen 2

**Screen 4 — Checkpoint 2: Insight Selection**
- "Sélectionnez les insights à inclure dans votre tableau de bord"
- Checklist of insights (pre-checked, user can deselect)
- Each insight shows: table, column, finding summary
- "Générer le tableau de bord" → POST /checkpoint2/{id} → back to Screen 2

**Screen 5 — Result**
- Green checkmark + "Votre tableau de bord est prêt"
- "Ouvrir dans Grist" button → external link to doc URL
- Summary: pages created (list)
- "Nouvelle analyse" → reload to Screen 1

### Error Handling

- `error` SSE event → red banner with message, "Réessayer" button
- Upload validation: only `.xlsx` accepted, max 50 MB (client-side check)
- Session timeout: 30 minutes (server-side cleanup)

---

## Integration with Existing Pipeline

`pipeline_runner.py` instantiates `PipelineOrchestrator` with a `WebCheckpointHandler` that:
1. Puts checkpoint data into the session's `event_queue`
2. Blocks on a `threading.Event`

`session.py` holds per-session state:
```python
@dataclass
class PipelineSession:
    event_queue: queue.Queue
    checkpoint1_event: threading.Event
    checkpoint1_response: dict | None
    checkpoint2_event: threading.Event
    checkpoint2_response: dict | None
    result: dict | None
    error: str | None
```

No persistent storage — all in-memory. Single-user or small-team use only (no auth layer in v1).

---

## Entry Point

```bash
uv run uvicorn webui.server:app --host 0.0.0.0 --port 8000
```

Or a convenience script `web.py` at project root:
```bash
uv run python web.py
```

---

## Out of Scope (v1)

- Authentication / multi-user isolation
- Persistent session storage (Redis, DB)
- Mobile-responsive layout
- Dark mode
- Progress cancellation
- Multiple concurrent uploads per session
