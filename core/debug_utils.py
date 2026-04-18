"""Debug output utility for pipeline steps."""

from __future__ import annotations
import json
from typing import Any


def debug_print(label: str, data: Any, enabled: bool = False) -> None:
    """Print step output when debug mode is active.

    Args:
        label: Step name shown in header
        data: Object supporting model_dump() (Pydantic), to_json(), dict, or str
        enabled: If False, no-op
    """
    if not enabled:
        return
    print(f"\n[DEBUG {label}]")
    if hasattr(data, "model_dump"):
        print(json.dumps(data.model_dump(), indent=2, ensure_ascii=False, default=str))
    elif hasattr(data, "to_json"):
        print(data.to_json())
    elif isinstance(data, dict):
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        print(str(data))
