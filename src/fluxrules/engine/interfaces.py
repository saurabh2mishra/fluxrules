from __future__ import annotations

from typing import Protocol

from fluxrules.domain.models import EvaluationResult, Ruleset


class EnginePort(Protocol):
    def evaluate(self, ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult: ...


class CompilerPort(Protocol):
    def compile(self, ruleset: Ruleset) -> Ruleset: ...
