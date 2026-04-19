from __future__ import annotations

from typing import Protocol

from fluxrules.domain.models import EvaluationResult, Ruleset


class EngineContract(Protocol):
    """Stable protocol used to keep Python and Rust engines compatible."""

    def evaluate(self, ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult: ...


ERROR_CODES = {
    "INVALID_RULE": "Invalid rule definition",
    "UNKNOWN_OPERATOR": "Predicate operator is not supported",
}
