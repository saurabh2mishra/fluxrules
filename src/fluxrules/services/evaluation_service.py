"""Evaluation service - solely responsible for rule evaluation."""

from __future__ import annotations

from fluxrules.domain.models import EvaluationResult, Ruleset
from fluxrules.engine.interfaces import EnginePort


class EvaluationService:
    """Evaluates rules against facts using a pluggable engine.

    Single responsibility: orchestrate fact evaluation without
    concern for persistence, validation, or auditing.
    """

    def __init__(self, engine: EnginePort) -> None:
        self.engine = engine

    def evaluate(self, ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult:
        """Evaluate a ruleset against facts."""
        return self.engine.evaluate(ruleset, facts)
