from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Activation:
    rule_id: str
    priority: int
    matched_facts: List[Dict[str, Any]] = field(default_factory=list)
    specificity: int = 0
    recency: int = 0
