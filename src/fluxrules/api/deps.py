from __future__ import annotations

from fluxrules.adapters.repository.in_memory import InMemoryExecutionStore, InMemoryRulesetRepository
from fluxrules.engine.interpreter import InterpreterEngine
from fluxrules.services.rule_service import RuleService


_service: RuleService | None = None


def get_rule_service() -> RuleService:
    global _service
    if _service is None:
        _service = RuleService(
            engine=InterpreterEngine(),
            repository=InMemoryRulesetRepository(),
            execution_store=InMemoryExecutionStore(),
        )
    return _service
