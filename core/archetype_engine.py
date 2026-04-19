"""Archetype Engine — dispatches DashboardPlan to the correct archetype module.

Usage:
    engine = ArchetypeEngine(api)
    created_pages = engine.apply(doc_id, classification, dashboard_plan)
"""

from __future__ import annotations
import logging
from core.grist_api import GristAPI
from core.domain_classifier import ClassificationResult
from core.dashboard_composer import DashboardPlan
from core.visual_intents import VisualIntentPlan
from archetypes.base import BaseArchetype
from archetypes.generic import GenericArchetype
from archetypes.hr import HRArchetype
from archetypes.decisionnel import DecisionnelArchetype
from archetypes.support import SupportArchetype
from archetypes.student import StudentArchetype
from archetypes.si import SIArchetype
from archetypes.project import ProjectArchetype

logger = logging.getLogger(__name__)

ARCHETYPE_MAP: dict[str, type[BaseArchetype]] = {
    "HR":          HRArchetype,
    "DECISIONNEL": DecisionnelArchetype,
    "SUPPORT":     SupportArchetype,
    "STUDENT":     StudentArchetype,
    "SI":          SIArchetype,
    "PROJECT":     ProjectArchetype,
    "GENERIC":     GenericArchetype,
}


class ArchetypeEngine:
    """Dispatches a DashboardPlan to the appropriate archetype template."""

    def __init__(self, api: GristAPI):
        self.api = api

    def apply(
        self,
        doc_id: str,
        classification: ClassificationResult,
        plan: DashboardPlan,
        visual_intents: VisualIntentPlan | None = None,
    ) -> list[str]:
        """Apply the archetype corresponding to classification.archetype.

        Falls back to GenericArchetype if the archetype string is unrecognised.

        Returns:
            List of created page names. Empty list if the archetype fails entirely.
        """
        archetype_cls = ARCHETYPE_MAP.get(classification.archetype, GenericArchetype)
        archetype = archetype_cls()
        logger.info(
            "Applying archetype %s via %s",
            classification.archetype, archetype_cls.__name__,
        )
        try:
            return archetype.apply(self.api, doc_id, classification, plan, visual_intents)
        except Exception as exc:
            logger.error("ArchetypeEngine.apply failed: %s", exc)
            return []
