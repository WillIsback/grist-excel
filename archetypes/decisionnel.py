"""DECISIONNEL archetype — Business Intelligence / Analytics domain."""
from __future__ import annotations
import logging
from archetypes.hr import HRArchetype
logger = logging.getLogger(__name__)

class DecisionnelArchetype(HRArchetype):
    """DECISIONNEL archetype: analytics dashboard + raw data table."""
