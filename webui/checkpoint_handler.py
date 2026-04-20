"""Checkpoint handler that blocks a pipeline thread and emits SSE events."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from core.checkpoint import ClassificationFeedback, InsightFeedback
from core.domain_classifier import ArchetypeLiteral
from webui.session import PipelineSession

if TYPE_CHECKING:
    from core.data_analyzer import DataProfile
    from core.domain_classifier import ClassificationResult
    from core.insight_extractor import InsightReport


class WebCheckpointHandler:
    """Satisfies CheckpointHandler protocol; communicates via session queues."""

    def __init__(self, session: PipelineSession) -> None:
        self._session = session

    def on_classification(
        self,
        result: "ClassificationResult",
        profile: "DataProfile",
    ) -> ClassificationFeedback:
        payload = {
            "archetype": result.archetype,
            "confidence": result.confidence,
            "table_mapping": result.table_mapping,
            "archetypes": ["HR", "DECISIONNEL", "SUPPORT", "STUDENT", "SI", "PROJECT", "GENERIC"],
        }
        self._session.event_queue.put(("checkpoint_1", json.dumps(payload)))
        self._session.checkpoint1_event.wait()
        self._session.checkpoint1_event.clear()

        resp = self._session.checkpoint1_response or {}
        archetype = resp.get("archetype", result.archetype)
        user_intent = resp.get("user_intent", "")
        return ClassificationFeedback(
            confirmed_archetype=cast(ArchetypeLiteral, archetype),
            user_intent=user_intent,
        )

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

        resp = self._session.checkpoint2_response or {}
        selected = resp.get("selected_indices", list(range(len(report.insights))))
        return InsightFeedback(selected_indices=selected)
