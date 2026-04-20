"""Tests for in-memory session store."""
import threading
import pytest
from webui.session import SessionStore, PipelineSession


def test_create_and_get_session():
    store = SessionStore()
    sid = store.create()
    session = store.get(sid)
    assert session is not None
    assert isinstance(session.checkpoint1_event, threading.Event)
    assert isinstance(session.checkpoint2_event, threading.Event)
    assert session.checkpoint1_response is None
    assert session.checkpoint2_response is None
    assert session.result is None
    assert session.error is None


def test_get_unknown_session_returns_none():
    store = SessionStore()
    assert store.get("nonexistent-id") is None


def test_session_ids_are_unique():
    store = SessionStore()
    ids = {store.create() for _ in range(10)}
    assert len(ids) == 10


def test_delete_session():
    store = SessionStore()
    sid = store.create()
    store.delete(sid)
    assert store.get(sid) is None
