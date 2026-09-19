"""Stateful evaluation sessions with save/restore (snapshot) support."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fluxrules.domain.models import EvaluationResult
    from fluxrules.services.rule_service import RuleService


@dataclass
class SessionSnapshot:
    """Immutable, JSON-serialisable snapshot of session state."""

    execution_id: str
    ruleset_id: int | str
    facts: dict[str, Any]
    timestamp: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str) -> SessionSnapshot:
        """Deserialise from a JSON string."""
        data = json.loads(json_str)
        return cls(**data)


class EvaluationSession:
    """Stateful rule-evaluation session.

    Typical usage::

        session = service.create_session("order_rules")
        session.add_fact("amount", 5000)
        snapshot = session.save()

        # Later …
        session2 = EvaluationSession.restore(snapshot, service)
        result = session2.evaluate()
    """

    def __init__(self, ruleset_id: int | str, service: RuleService) -> None:
        self.ruleset_id = ruleset_id
        self.service = service
        self.facts: dict[str, Any] = {}
        self.result: EvaluationResult | None = None
        self.execution_id: str = str(uuid.uuid4())
        self.metadata: dict[str, Any] = {}

    # Fact management

    def add_fact(self, key: str, value: Any) -> None:
        """Add or update a single fact."""
        self.facts[key] = value

    def add_facts(self, facts: dict[str, Any]) -> None:
        """Merge multiple facts into the session."""
        self.facts.update(facts)

    def remove_fact(self, key: str) -> None:
        """Remove a fact by key (no-op if missing)."""
        self.facts.pop(key, None)

    def clear_facts(self) -> None:
        """Remove all facts."""
        self.facts.clear()

    # Evaluation

    def evaluate(self) -> EvaluationResult:
        """Evaluate the ruleset with the current facts."""
        self.result = self.service.evaluate_ruleset(self.ruleset_id, self.facts)
        return self.result

    # Snapshot save / restore

    def save(self) -> str:
        """Create a JSON snapshot of the current session state."""
        snapshot = SessionSnapshot(
            execution_id=self.execution_id,
            ruleset_id=self.ruleset_id,
            facts=self.facts.copy(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=self.metadata.copy(),
        )
        return snapshot.to_json()

    @classmethod
    def restore(cls, json_snapshot: str, service: RuleService) -> EvaluationSession:
        """Reconstruct a session from a previously saved JSON snapshot."""
        snapshot = SessionSnapshot.from_json(json_snapshot)
        session = cls(snapshot.ruleset_id, service)
        session.facts = snapshot.facts
        session.execution_id = snapshot.execution_id
        session.metadata = snapshot.metadata
        return session
