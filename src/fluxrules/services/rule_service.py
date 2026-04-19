from __future__ import annotations

from fluxrules.adapters.observability.noop import NoopTracer
from fluxrules.adapters.repository.in_memory import InMemoryExecutionStore, InMemoryRulesetRepository
from fluxrules.domain.models import EvaluationResult, Ruleset
from fluxrules.engine.interfaces import EnginePort
from fluxrules.engine.interpreter import InterpreterEngine
from fluxrules.ports.execution_store import ExecutionStorePort
from fluxrules.ports.observability import TracerPort
from fluxrules.ports.repository import RulesetRepositoryPort
from fluxrules.services.validation_service import ValidationService


class RuleService:
    def __init__(
        self,
        engine: EnginePort,
        repository: RulesetRepositoryPort,
        execution_store: ExecutionStorePort,
        tracer: TracerPort | None = None,
    ):
        self.engine = engine
        self.repository = repository
        self.execution_store = execution_store
        self.tracer = tracer or NoopTracer()
        self.validation = ValidationService()

    @classmethod
    def default(cls) -> "RuleService":
        return cls(
            engine=InterpreterEngine(),
            repository=InMemoryRulesetRepository(),
            execution_store=InMemoryExecutionStore(),
            tracer=NoopTracer(),
        )

    def validate(self, ruleset: Ruleset) -> list[str]:
        return self.validation.validate_ruleset(ruleset)

    def evaluate(self, ruleset_id: str, facts: dict[str, object]) -> EvaluationResult:
        ruleset = self.repository.get(ruleset_id)
        if ruleset is None:
            raise KeyError(f"Unknown ruleset '{ruleset_id}'")
        result = self.evaluate_inline(ruleset, facts)
        self.execution_store.save(result)
        return result

    def evaluate_inline(self, ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult:
        issues = self.validate(ruleset)
        if issues:
            raise ValueError(f"Ruleset validation failed: {issues}")
        self.tracer.on_evaluation_start(ruleset.id)
        result = self.engine.evaluate(ruleset, facts)
        self.tracer.on_evaluation_end(ruleset.id, len(result.matched_rule_ids))
        return result

    def explain(self, execution_id: str) -> EvaluationResult:
        result = self.execution_store.get(execution_id)
        if result is None:
            raise KeyError(f"Unknown execution '{execution_id}'")
        return result

    def simulate(self, ruleset_id: str, samples: list[dict[str, object]]) -> list[EvaluationResult]:
        ruleset = self.repository.get(ruleset_id)
        if ruleset is None:
            raise KeyError(f"Unknown ruleset '{ruleset_id}'")
        return [self.evaluate_inline(ruleset, facts) for facts in samples]

    def save_ruleset(self, ruleset: Ruleset) -> None:
        self.repository.save(ruleset)
