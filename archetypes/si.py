"""SI archetype — Information Systems / IT assets domain."""
from __future__ import annotations
import logging
from archetypes.hr import HRArchetype
logger = logging.getLogger(__name__)

class SIArchetype(HRArchetype):
    """SI archetype: inventory table + SI dashboard + incident form."""
