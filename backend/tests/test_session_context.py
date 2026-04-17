from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.execution.session_context import SessionContext


class TestSessionContext:
    def test_session_lifecycle(self):
        session = SessionContext(
            session_id="s-1",
            group="fraud",
            created_at=datetime.now(timezone.utc),
            ttl_seconds=300,
            config={"max_facts": 10, "memory_budget_bytes": 10_000},
        )

        result1 = session.assert_fact("f-1", {"fact_id": "f-1", "amount": 100})
        result2 = session.assert_fact("f-2", {"fact_id": "f-2", "amount": 200})

        assert result1.asserted is True
        assert result2.asserted is True
        assert session.get_stats().facts_count == 2

        retract = session.retract_fact("f-1")
        assert retract.retracted is True
        assert session.get_stats().facts_count == 1

        session.destroy()
        stats = session.get_stats()
        assert stats.destroyed is True
        assert stats.facts_count == 0

        with pytest.raises(RuntimeError):
            session.assert_fact("f-3", {"fact_id": "f-3", "amount": 300})

    def test_enforces_memory_budget_with_eviction(self):
        session = SessionContext(
            session_id="s-2",
            group="fraud",
            created_at=datetime.now(timezone.utc),
            ttl_seconds=300,
            config={"max_facts": 10, "memory_budget_bytes": 120},
        )

        # First assert should fit comfortably.
        first = session.assert_fact("old", {"fact_id": "old", "payload": "x" * 60})
        assert first.asserted is True
        assert first.evicted_fact_ids == []

        # Second assert should force eviction of the oldest fact due to budget.
        second = session.assert_fact("new", {"fact_id": "new", "payload": "y" * 60})
        assert second.asserted is True
        assert "old" in second.evicted_fact_ids
        assert "old" not in session.working_memory.facts()
        assert "new" in session.working_memory.facts()

        stats = session.get_stats()
        assert stats.memory_bytes <= stats.memory_budget_bytes

    def test_ttl_expiration_behavior(self):
        now = datetime.now(timezone.utc)

        expired_session = SessionContext(
            session_id="s-expired",
            group="fraud",
            created_at=now - timedelta(seconds=61),
            ttl_seconds=60,
        )
        active_session = SessionContext(
            session_id="s-active",
            group="fraud",
            created_at=now,
            ttl_seconds=60,
        )

        assert expired_session.is_expired() is True
        assert expired_session.get_stats().is_expired is True

        assert active_session.is_expired() is False
        assert active_session.get_stats().is_expired is False
