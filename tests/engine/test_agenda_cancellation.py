"""Tests for Agenda unscheduling.

Tests the ability to cancel pending activations from the agenda,
used when fact changes invalidate rules before they fire.
"""

import pytest

from fluxrules.engine.infrastructure.agenda import Agenda


class TestAgendaCancellation:
    """Tests for agenda cancellation feature."""

    def test_cancel_single_activation(self):
        """Test cancelling a single rule activation."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)

        assert not agenda.is_empty()

        agenda.cancel_activation(1)

        # When popping, it should skip the cancelled activation
        act = agenda.next_activation()
        assert act is None

    def test_cancel_one_of_many(self):
        """Test cancelling one activation when multiple exist."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)
        agenda.add_activation(2, priority=2)
        agenda.add_activation(3, priority=1)

        agenda.cancel_activation(2)

        # Pop first non-cancelled
        act1 = agenda.next_activation()
        assert act1.rule_id in [1, 3]  # Not 2

        # Pop second non-cancelled
        act2 = agenda.next_activation()
        assert act2.rule_id in [1, 3]

        # No more activations
        act3 = agenda.next_activation()
        assert act3 is None

    def test_cancel_all_activations(self):
        """Test cancelling all activations results in empty agenda on pop."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)
        agenda.add_activation(2, priority=2)
        agenda.add_activation(3, priority=1)

        agenda.cancel_activation(1)
        agenda.cancel_activation(2)
        agenda.cancel_activation(3)

        # All activations cancelled
        act = agenda.next_activation()
        assert act is None

    def test_cancel_non_existent_does_not_error(self):
        """Test that cancelling a non-existent rule doesn't error."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)

        # Cancel a rule that was never added - should not error
        agenda.cancel_activation(999)

        # Original rule should still be there
        act = agenda.next_activation()
        assert act.rule_id == 1

    def test_cancel_already_popped(self):
        """Test cancelling a rule that's already been popped."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)

        # Pop it
        act = agenda.next_activation()
        assert act.rule_id == 1

        # Try to cancel it
        agenda.cancel_activation(1)

        # No effect
        act2 = agenda.next_activation()
        assert act2 is None


class TestAgendaCancellationOrder:
    """Tests for proper conflict resolution with cancellation."""

    def test_priority_respected_with_cancellation(self):
        """Test that priority is still respected when some rules are cancelled."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)
        agenda.add_activation(2, priority=3)
        agenda.add_activation(3, priority=2)

        # Cancel the highest priority
        agenda.cancel_activation(2)

        # Should get priority 3 (rule 3)
        act1 = agenda.next_activation()
        assert act1.rule_id == 3

        # Then priority 1 (rule 1)
        act2 = agenda.next_activation()
        assert act2.rule_id == 1


class TestAgendaCancellationStreaming:
    """Tests simulating streaming mode usage with fact changes."""

    def test_streaming_fact_change_scenario(self):
        """Test a streaming scenario where facts change and rules are cancelled."""
        agenda = Agenda()

        # Initial evaluation finds rules 1, 2, 3 to fire
        agenda.add_activation(1, priority=1)
        agenda.add_activation(2, priority=1)
        agenda.add_activation(3, priority=1)

        # Facts change: rule 2 is no longer applicable
        agenda.cancel_activation(2)

        # Fire remaining rules
        fired = []
        while True:
            act = agenda.next_activation()
            if act is None:
                break
            fired.append(act.rule_id)

        assert 2 not in fired
        assert set(fired) == {1, 3}

    def test_interleaved_cancel_and_pop(self):
        """Test interleaving cancellations with pops."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)
        agenda.add_activation(2, priority=1)
        agenda.add_activation(3, priority=1)
        agenda.add_activation(4, priority=1)

        # Pop one
        act1 = agenda.next_activation()
        assert act1.rule_id in [1, 2, 3, 4]

        # Cancel another
        agenda.cancel_activation(3)

        # Pop another
        act2 = agenda.next_activation()
        assert act2.rule_id != 3

        # Cancel the first popped one (no effect)
        agenda.cancel_activation(act1.rule_id)

        # Pop remaining
        remaining = []
        while True:
            act = agenda.next_activation()
            if act is None:
                break
            remaining.append(act.rule_id)

        assert 3 not in remaining


class TestAgendaClear:
    """Tests for clearing with cancelled rules."""

    def test_clear_removes_cancelled(self):
        """Test that clear() resets cancelled set."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)
        agenda.cancel_activation(1)

        agenda.clear()

        # Cancelled set should be empty
        assert len(agenda._cancelled) == 0


class TestAgendaIntegration:
    """Integration tests with normal agenda operations."""

    def test_is_empty_with_all_cancelled(self):
        """Test that is_empty still returns False even if all are cancelled.

        Note: is_empty checks heap size, not whether all are cancelled.
        """
        agenda = Agenda()
        agenda.add_activation(1, priority=1)
        agenda.cancel_activation(1)

        # Heap still has one item
        assert not agenda.is_empty()

        # But popping returns None
        act = agenda.next_activation()
        assert act is None

    def test_len_with_cancellations(self):
        """Test __len__ returns heap size, not net non-cancelled count."""
        agenda = Agenda()
        agenda.add_activation(1, priority=1)
        agenda.add_activation(2, priority=1)
        agenda.cancel_activation(1)

        # __len__ returns heap size
        assert len(agenda) == 2

    def test_strategy_with_cancellation(self):
        """Test that conflict resolution strategy still works."""
        from fluxrules.engine.infrastructure.agenda import SalienceRecencyStrategy

        agenda = Agenda()
        strategy = SalienceRecencyStrategy()
        agenda.set_strategy(strategy)

        agenda.add_activation(1, priority=1)
        agenda.add_activation(2, priority=3)
        agenda.add_activation(3, priority=2)

        agenda.cancel_activation(2)

        # Should respect priority for non-cancelled
        act = agenda.next_activation()
        assert act.rule_id == 3  # Priority 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
