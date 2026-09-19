"""Repository for persisting and loading execution traces."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from fluxrules.api.database import Base
from fluxrules.domain.models import EvaluationResult

logger = logging.getLogger("fluxrules.persistence")


class EvaluationResultORM(Base):
    """ORM model for persisted evaluation results."""

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    ruleset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    matched_rule_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    actions: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    trace: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ExecutionRepository:
    """Database-backed repository for :class:`EvaluationResult`."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, result: EvaluationResult) -> None:
        """Persist an evaluation result."""
        orm = EvaluationResultORM(
            execution_id=result.execution_id,
            ruleset_id=str(result.ruleset_group) if hasattr(result, "ruleset_group") else None,
            matched_rule_ids=json.dumps(result.matched_rule_ids),
            actions=json.dumps(result.actions),
            trace=json.dumps(result.trace),
        )
        self.db.merge(orm)
        self.db.commit()

    def load(self, execution_id: str) -> EvaluationResult | None:
        """Load an evaluation result by execution ID."""
        orm = (
            self.db.query(EvaluationResultORM)
            .filter(EvaluationResultORM.execution_id == execution_id)
            .first()
        )
        if orm is None:
            return None
        return EvaluationResult(
            execution_id=orm.execution_id,
            ruleset_group=orm.ruleset_id or "",
            matched_rule_ids=json.loads(orm.matched_rule_ids),
            actions=json.loads(orm.actions),
            trace=json.loads(orm.trace),
        )
