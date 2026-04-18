"""HR archetype — Human Resources domain.

Semantic roles: employees (required), absences (optional), evaluations (optional)
Renders every page and section from the DashboardPlan.
"""

from __future__ import annotations
import logging
from archetypes.generic import GenericArchetype

logger = logging.getLogger(__name__)


class HRArchetype(GenericArchetype):
    """HR archetype: renders DashboardPlan pages for HR domain."""
