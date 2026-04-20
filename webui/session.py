"""In-memory pipeline session store."""
from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineSession:
    event_queue: queue.Queue = field(default_factory=queue.Queue)
    checkpoint1_event: threading.Event = field(default_factory=threading.Event)
    checkpoint1_response: dict[str, Any] | None = None
    checkpoint2_event: threading.Event = field(default_factory=threading.Event)
    checkpoint2_response: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


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
