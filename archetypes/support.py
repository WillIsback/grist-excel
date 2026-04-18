"""SUPPORT archetype — Customer support / ticketing domain."""
from __future__ import annotations
import logging
from archetypes.hr import HRArchetype
logger = logging.getLogger(__name__)

class SupportArchetype(HRArchetype):
    """SUPPORT archetype: ticket card list + dashboard + form."""
