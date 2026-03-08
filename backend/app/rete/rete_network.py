from __future__ import annotations

from typing import Any, Dict, List

from app.engine.rete_network import ReteEngine as LegacyReteEngine


class ScalableReteNetwork:
    """Compatibility wrapper extending the existing RETE implementation."""

    def __init__(self):
        self._engine = LegacyReteEngine()

    def load_rules(self, rules: List[Dict[str, Any]]) -> None:
        self._engine.load_rules(rules)

    def evaluate(self, fact: Dict[str, Any]) -> Dict[str, Any]:
        return self._engine.evaluate(fact)

    def get_stats(self) -> Dict[str, Any]:
        return self._engine.get_stats()

    def invalidate(self) -> None:
        self._engine.invalidate()
