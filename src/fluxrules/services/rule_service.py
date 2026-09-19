from __future__ import annotations

from typing import TYPE_CHECKING

from fluxrules.adapters.observability.noop import NoopTracer
from fluxrules.adapters.repository.in_memory import (
    InMemoryExecutionStore,
    InMemoryRulesetRepository,
)
from fluxrules.domain.models import EvaluationResult, Ruleset
from fluxrules.engine.interfaces import EnginePort
from fluxrules.ports.execution_store import ExecutionStorePort
from fluxrules.ports.observability import TracerPort
from fluxrules.ports.repository import RulesetRepositoryPort
from fluxrules.services.reference_evaluator import ReferenceEvaluator
from fluxrules.services.validation_service import ValidationService

if TYPE_CHECKING:
    from fluxrules.adapters.persistence.sqlalchemy_adapter import (
        SQLAlchemyPersistenceAdapter,
    )
    from fluxrules.persistence.execution_repository import ExecutionRepository
    from fluxrules.services.session import EvaluationSession


def create_persistent_service(db_url: str, *, tenant_id: str = "default") -> RuleService:
    """Create a RuleService backed by a SQLite/PostgreSQL database.

    This factory:
    1. Creates a SQLAlchemy engine from the given URL
    2. Creates tables if they don't exist
    3. Loads all enabled rules from the DB into the in-memory cache
    4. Persists new rulesets automatically on ``persist()``

    Args:
        db_url: SQLAlchemy database URL (e.g. ``"sqlite:///rules.db"``)
        tenant_id: Logical tenant namespace - rulesets are isolated per tenant.
            Defaults to ``"default"`` for single-tenant deployments.

    Returns:
        A fully initialized RuleService with persistence enabled.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url)

    # Create tables if they don't exist
    from fluxrules.api.database import Base

    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    from fluxrules.adapters.persistence.sqlalchemy_adapter import (
        SQLAlchemyPersistenceAdapter,
    )
    from fluxrules.persistence.execution_repository import ExecutionRepository

    persistence = SQLAlchemyPersistenceAdapter(db)
    service = RuleService.create(tenant_id=tenant_id)
    service._persistence_enabled = True
    service._repository = persistence
    service._execution_repository = ExecutionRepository(db)

    # Auto-load all rulesets for this tenant from DB into in-memory cache
    all_rulesets = persistence.load_all_rulesets()
    for rs in all_rulesets.values():
        service.repository.save(rs)

    return service


class RuleService:
    _default_instance: RuleService | None = None

    def __init__(
        self,
        engine: EnginePort | None = None,
        repository: RulesetRepositoryPort | None = None,
        execution_store: ExecutionStorePort | None = None,
        tracer: TracerPort | None = None,
        tenant_id: str = "default",
    ):
        self.engine = engine or ReferenceEvaluator()
        self.repository = repository or InMemoryRulesetRepository()
        self.execution_store = execution_store or InMemoryExecutionStore()
        self.tracer = tracer or NoopTracer()
        self.validation = ValidationService()
        self.tenant_id = tenant_id
        self._persistence_enabled = False
        self._repository: SQLAlchemyPersistenceAdapter | None = (
            None  # DB-backed repository when persistence is enabled
        )
        self._execution_repository: ExecutionRepository | None = None  # DB-backed execution store

    @classmethod
    def default(cls) -> RuleService:
        if cls._default_instance is None:
            cls._default_instance = cls(
                engine=ReferenceEvaluator(),
                repository=InMemoryRulesetRepository(),
                execution_store=InMemoryExecutionStore(),
                tracer=NoopTracer(),
            )
        return cls._default_instance

    @classmethod
    def create(
        cls,
        engine: EnginePort | None = None,
        repository: RulesetRepositoryPort | None = None,
        execution_store: ExecutionStorePort | None = None,
        tracer: TracerPort | None = None,
        tenant_id: str = "default",
    ) -> RuleService:
        """Create a fresh RuleService instance (no shared state).

        Args:
            tenant_id: Logical tenant namespace for ruleset isolation.
        """
        return cls(
            engine=engine,
            repository=repository,
            execution_store=execution_store,
            tracer=tracer,
            tenant_id=tenant_id,
        )

    @classmethod
    def _reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._default_instance = None

    @classmethod
    def with_persistence(cls, db_session) -> RuleService:
        """Create a RuleService backed by a database session."""
        from fluxrules.adapters.persistence.sqlalchemy_adapter import (
            SQLAlchemyPersistenceAdapter,
        )

        service = cls()
        service._persistence_enabled = True
        service._repository = SQLAlchemyPersistenceAdapter(db_session)
        return service

    def validate(self, ruleset: Ruleset) -> list[str]:
        return self.validation.validate_ruleset(ruleset)

    def evaluate_ruleset(self, ruleset_id, facts: dict[str, object]) -> EvaluationResult:
        """Evaluate a persisted ruleset against facts.

        Args:
            ruleset_id: Numeric ID or name of the ruleset.
            facts: Fact dictionary to evaluate against.

        Returns:
            EvaluationResult with matched rules, actions, and execution trace.
        """
        ruleset = self.repository.get(ruleset_id)
        if ruleset is None and self._persistence_enabled and self._repository:
            if isinstance(ruleset_id, str):
                ruleset = self._repository.load_ruleset(ruleset_id)
        if ruleset is None:
            raise KeyError(f"Unknown ruleset '{ruleset_id}'")
        result = self.evaluate_inline(ruleset, facts)
        self.execution_store.save(result)
        if self._persistence_enabled and self._execution_repository:
            self._execution_repository.save(result)
        return result

    def evaluate_inline(self, ruleset: Ruleset, facts: dict[str, object]) -> EvaluationResult:
        # INFO-level findings are observations, not defects. A rule whose DSL
        # is valid but not expressible as a flat condition list reports one;
        # escalating that to a hard failure rejected perfectly good OR rules.
        from fluxrules.ports.validation import ValidationSeverity

        issues = [
            issue.message
            for issue in self.validation.validate_ruleset_detailed(ruleset)
            if issue.severity is not ValidationSeverity.INFO
        ]
        if issues:
            raise ValueError(f"Ruleset validation failed: {issues}")
        self.tracer.on_evaluation_start(ruleset.group)
        result = self.engine.evaluate(ruleset, facts)
        self.tracer.on_evaluation_end(ruleset.group, len(result.matched_rule_ids))
        return result

    def explain(self, execution_id: str) -> EvaluationResult:
        result = self.execution_store.get(execution_id)
        if result is None and self._persistence_enabled and self._execution_repository:
            result = self._execution_repository.load(execution_id)
        if result is None:
            raise KeyError(f"Unknown execution '{execution_id}'")
        return result

    def simulate(self, ruleset_id, samples: list[dict[str, object]]) -> list[EvaluationResult]:
        ruleset = self.repository.get(ruleset_id)
        if ruleset is None:
            raise KeyError(f"Unknown ruleset '{ruleset_id}'")
        return [self.evaluate_inline(ruleset, facts) for facts in samples]

    def persist(self, ruleset: Ruleset) -> None:
        """Persist a ruleset to the repository (and database if enabled).

        Args:
            ruleset: The ruleset to persist.
        """
        self.repository.save(ruleset)
        if self._persistence_enabled and self._repository:
            self._repository.save_ruleset(ruleset)

    def create_session(self, ruleset_id: int | str) -> EvaluationSession:
        """Create a new stateful evaluation session for the given ruleset."""
        from fluxrules.services.session import EvaluationSession

        return EvaluationSession(ruleset_id, self)

    def get_ruleset(self, ruleset_id: int | str) -> Ruleset | None:
        """Get a ruleset by group name from the in-memory repository."""
        return self.repository.get(ruleset_id)

    def get_ruleset_by_name(self, name: str) -> Ruleset | None:
        """Load a ruleset by group name from the database."""
        if self._persistence_enabled and self._repository:
            return self._repository.load_ruleset(name)
        return None
