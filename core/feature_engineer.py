"""Agent 3.5 — Feature Engineer.

Plans and applies Grist formula columns derived from LLM insights.
Two-phase:
  1. plan() — LLM generates FeaturePlan (formula columns to create)
  2. apply() — writes formula cols to live Grist document via PATCH API
"""

from __future__ import annotations

from pydantic import BaseModel, Field

logger = __name__


class FormulaColumn(BaseModel):
    """A derived Grist column defined by a Python formula."""

    table: str = Field(description="Semantic table role (key in table_mapping, e.g. 'employees')")
    col_id: str = Field(description="Grist column ID — ASCII only, no spaces")
    label: str = Field(description="Human-readable label (French)")
    type: str = Field(description="Grist type: Toggle, Int, Numeric, Text")
    formula: str = Field(description="Grist Python formula using $ColName and Table.lookupRecords() syntax")


class FeaturePlan(BaseModel):
    """Plan of derived columns to create in the Grist document."""

    features: list[FormulaColumn] = Field(
        default_factory=list,
        max_length=6,
        description="Derived columns to create (0–6)",
    )
