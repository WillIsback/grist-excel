"""Integration tests for FastAPI web server endpoints."""
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from webui.server import app, store


@pytest.fixture
def client():
    return TestClient(app)


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_upload_rejects_non_xlsx(client):
    resp = client.post("/upload", files={"file": ("data.csv", b"a,b\n1,2", "text/csv")})
    assert resp.status_code == 400


def test_upload_accepts_xlsx_and_returns_session_id(client):
    xlsx_magic = b"PK\x03\x04" + b"\x00" * 26
    with patch("webui.server.start_pipeline_thread"):
        resp = client.post("/upload", files={"file": ("test.xlsx", xlsx_magic, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert resp.status_code == 200
    body = resp.json()
    assert "session_id" in body


def test_stream_unknown_session_returns_404(client):
    resp = client.get("/stream/nonexistent-id")
    assert resp.status_code == 404


def test_checkpoint1_unknown_session_returns_404(client):
    resp = client.post("/checkpoint1/nonexistent-id", data={"archetype": "HR", "user_intent": ""})
    assert resp.status_code == 404


def test_checkpoint2_unknown_session_returns_404(client):
    resp = client.post("/checkpoint2/nonexistent-id", data={"selected_indices": "[0,1]"})
    assert resp.status_code == 404


def test_checkpoint1_sets_response_and_unblocks(client):
    sid = store.create()
    session = store.get(sid)

    resp = client.post(f"/checkpoint1/{sid}", data={"archetype": "HR", "user_intent": "test intent"})
    assert resp.status_code == 200
    assert session.checkpoint1_response == {"archetype": "HR", "user_intent": "test intent"}
    assert session.checkpoint1_event.is_set()


def test_checkpoint2_parses_indices(client):
    sid = store.create()
    session = store.get(sid)

    resp = client.post(f"/checkpoint2/{sid}", data={"selected_indices": "[0, 2]"})
    assert resp.status_code == 200
    assert session.checkpoint2_response == {"selected_indices": [0, 2]}


def test_result_returns_202_while_running(client):
    sid = store.create()
    resp = client.get(f"/result/{sid}")
    assert resp.status_code == 202


def test_result_returns_doc_url_when_complete(client):
    sid = store.create()
    session = store.get(sid)
    session.result = {"doc_url": "http://grist/doc/abc", "pages": ["Dashboard"]}

    resp = client.get(f"/result/{sid}")
    assert resp.status_code == 200
    assert resp.json()["doc_url"] == "http://grist/doc/abc"


def test_checkpoint2_caches_full_insight_list():
    """After Checkpoint 2, session.cached_insights holds full InsightReport."""
    from core.insight_extractor import InsightEntry, InsightReport
    from webui.checkpoint_handler import WebCheckpointHandler
    from webui.session import SessionStore
    from unittest.mock import MagicMock

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

    profile_mock = MagicMock()
    handler.on_insights(report, profile_mock)

    assert session.cached_insights is not None
    assert len(session.cached_insights) == 2  # full list, not filtered
