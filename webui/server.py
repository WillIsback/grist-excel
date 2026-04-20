"""FastAPI web server for grist-excel UI."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from webui.session import SessionStore
from webui.pipeline_runner import start_pipeline_thread

BASE_DIR = Path(__file__).parent

app = FastAPI(title="grist-excel web UI")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
store = SessionStore()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/run", response_class=HTMLResponse)
async def run_page(request: Request):
    return templates.TemplateResponse(request, "run.html")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .xlsx sont acceptés.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 50 Mo).")
    sid = store.create()
    session = store.get(sid)
    start_pipeline_thread(session, data, file.filename)
    return JSONResponse({"session_id": sid})


@app.get("/stream/{sid}")
async def stream(sid: str):
    session = store.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session inconnue.")

    def event_generator():
        while True:
            event, data = session.event_queue.get()
            yield f"event: {event}\ndata: {data}\n\n"
            if event in ("complete", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/checkpoint1/{sid}")
async def checkpoint1(sid: str, archetype: str = Form(...), user_intent: str = Form("")):
    session = store.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session inconnue.")
    session.checkpoint1_response = {"archetype": archetype, "user_intent": user_intent}
    session.checkpoint1_event.set()
    return JSONResponse({"status": "ok"})


@app.post("/checkpoint2/{sid}")
async def checkpoint2(sid: str, selected_indices: str = Form(...)):
    session = store.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session inconnue.")
    try:
        indices = json.loads(selected_indices)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="selected_indices doit être un JSON array.")
    session.checkpoint2_response = {"selected_indices": indices}
    session.checkpoint2_event.set()
    return JSONResponse({"status": "ok"})


@app.get("/result/{sid}")
async def result(sid: str):
    session = store.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session inconnue.")
    if session.error:
        raise HTTPException(status_code=500, detail=session.error)
    if not session.result:
        raise HTTPException(status_code=202, detail="Pipeline en cours.")
    return JSONResponse(session.result)
