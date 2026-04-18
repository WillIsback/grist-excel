"""STUDENT archetype — Academic / education domain."""
from __future__ import annotations
import logging
from archetypes.hr import HRArchetype
logger = logging.getLogger(__name__)

class StudentArchetype(HRArchetype):
    """STUDENT archetype: student cards + grade summary + dashboard."""
