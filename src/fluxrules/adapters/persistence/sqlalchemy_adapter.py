"""SQLAlchemy-backed persistence adapter.

Isolates all ORM imports (fluxrules.api.models.*) to this adapter layer,
keeping the core and services layers free of database coupling.

Supports two construction modes:

1. **Lazy session binding** (preferred for DI / ServiceFactory)::

       adapter = SQLAlchemyPersistenceAdapter(
           session_provider=lambda: SessionLocal(),
       )

   The *session_provider* callable is invoked each time a database
   session is needed, enabling request-scoped session management in
   web frameworks like FastAPI.

2. **Direct session** (legacy / simple scripts)::

       adapter = SQLAlchemyPersistenceAdapter(db=my_session)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from fluxrules.domain.models import EngineRule, Ruleset
from fluxrules.persistence.mappers import domain_rule_to_orm, orm_rule_to_domain
from fluxrules.ports.persistence import RulePersistencePort

logger = logging.getLogger("fluxrules.adapters.persistence")


class SQLAlchemyPersistenceAdapter(RulePersistencePort):
    """Concrete persistence implementation using SQLAlchemy ORM.

    All ORM model imports are isolated here, so the core engine
    and services never depend on the API/database layer directly.

    Args:
        db: A pre-existing SQLAlchemy session (legacy mode).
        session_provider: A callable returning a SQLAlchemy ``Session``.
            When provided, the adapter calls it each time it needs a
            session.  This enables **lazy session binding** - the
            recommended pattern for ServiceFactory / DI usage.

    Raises:
        ValueError: If neither *db* nor *session_provider* is given.
    """

    def __init__(
        self,
        db: Session | None = None,
        *,
        session_provider: Callable[[], Session] | None = None,
    ) -> None:
        if db is None and session_provider is None:
            raise ValueError(
                "SQLAlchemyPersistenceAdapter requires either 'db' "
                "(a Session) or 'session_provider' (a callable)"
            )
        self._db = db
        self._session_provider = session_provider

    @property
    def db(self) -> Session:
        """Return the active database session.

        When a *session_provider* was supplied at construction time the
        provider is called to obtain a session.  Each write method captures
        this property **once** into a local variable so that add/commit/refresh
        all operate on the same session object — a plain ``sessionmaker``
        returns a new session on every call, so re-accessing the property
        inside a single operation would silently commit an empty transaction.
        """
        if self._session_provider is not None:
            return self._session_provider()
        assert self._db is not None
        return self._db

    # ── Write operations ─────────────────────────────────────────────────────

    def save_rule(self, rule: EngineRule, group: str = "", created_by: int | None = None) -> int:
        db = self.db  # capture once — session_provider may return a new session each call
        orm_rule = domain_rule_to_orm(rule, group=group, created_by=created_by)
        db.add(orm_rule)
        db.commit()
        db.refresh(orm_rule)
        return orm_rule.id

    def save_ruleset(self, ruleset: Ruleset, created_by: int | None = None) -> list[int]:
        ids: list[int] = []
        for rule in ruleset.rules:
            rid = self.save_rule(rule, group=ruleset.group, created_by=created_by)
            ids.append(rid)
        return ids

    def update_rule(self, rule_id: int, **kwargs) -> EngineRule | None:
        from fluxrules.api.models.rule import Rule as OrmRule

        db = self.db  # capture once — session_provider may return a new session each call
        orm_rule = db.query(OrmRule).filter(OrmRule.id == rule_id).first()
        if orm_rule is None:
            return None

        for key, value in kwargs.items():
            if key == "conditions" and isinstance(value, (list, tuple)):
                # Store a DSL tree, not a list of condition dicts: the column
                # holds exactly one shape.
                from fluxrules.domain.dsl.evaluator import conditions_to_dsl

                orm_rule.conditions = conditions_to_dsl(value)
            elif key == "conditions":
                orm_rule.conditions = value
            elif key == "actions" and isinstance(value, (list, tuple)):
                orm_rule.action = "\n".join(value)
            elif hasattr(orm_rule, key):
                setattr(orm_rule, key, value)

        orm_rule.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(orm_rule)
        return orm_rule_to_domain(orm_rule)

    def delete_rule(self, rule_id: int) -> bool:
        from fluxrules.api.models.rule import Rule as OrmRule

        db = self.db  # capture once — session_provider may return a new session each call
        orm_rule = db.query(OrmRule).filter(OrmRule.id == rule_id).first()
        if orm_rule is None:
            return False
        db.delete(orm_rule)
        db.commit()
        return True

    # ── Read operations ──────────────────────────────────────────────────────

    def load_rule(self, rule_id: int) -> EngineRule | None:
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rule = self.db.query(OrmRule).filter(OrmRule.id == rule_id).first()
        if orm_rule is None:
            return None
        return orm_rule_to_domain(orm_rule)

    def load_all_rules(self) -> list[EngineRule]:
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rules = self.db.query(OrmRule).order_by(OrmRule.priority.desc()).all()
        return [orm_rule_to_domain(r) for r in orm_rules]

    def load_ruleset(self, group: str) -> Ruleset:
        from fluxrules.api.models.rule import Rule as OrmRule

        orm_rules = (
            self.db.query(OrmRule)
            .filter(OrmRule.group == group)
            .order_by(OrmRule.priority.desc())
            .all()
        )
        rules = [orm_rule_to_domain(r) for r in orm_rules]
        return Ruleset(group=group, rules=tuple(rules))

    def load_all_rulesets(self) -> dict[str, Ruleset]:
        all_rules = self.load_all_rules()
        groups: dict[str, list[EngineRule]] = {}
        for r in all_rules:
            g = r.group or ""
            groups.setdefault(g, []).append(r)
        return {g: Ruleset(group=g, rules=tuple(rs)) for g, rs in groups.items()}
