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
