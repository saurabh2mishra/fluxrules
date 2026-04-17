from datetime import datetime, timedelta, timezone

from app.engine.sequence import SequenceEvaluator


def _fact(event: str, user_id: str, ts: datetime):
    return {
        "event": event,
        "user_id": user_id,
        "inserted_at": ts,
    }


def test_ordered_sequence_matches_once_completed():
    now = datetime.now(timezone.utc)
    evaluator = SequenceEvaluator(
        steps=[
            {"field": "event", "op": "==", "value": "login"},
            {"field": "event", "op": "==", "value": "purchase"},
        ],
        within_window_seconds=120,
        correlate_on=["user_id"],
    )

    assert evaluator.assert_fact(_fact("login", "u1", now)) == []

    matches = evaluator.assert_fact(_fact("purchase", "u1", now + timedelta(seconds=30)))
    assert len(matches) == 1
    assert [step["event"] for step in matches[0]] == ["login", "purchase"]


def test_out_of_order_does_not_match():
    now = datetime.now(timezone.utc)
    evaluator = SequenceEvaluator(
        steps=[
            {"field": "event", "op": "==", "value": "login"},
            {"field": "event", "op": "==", "value": "purchase"},
        ],
        within_window_seconds=120,
        correlate_on=["user_id"],
    )

    assert evaluator.assert_fact(_fact("purchase", "u1", now)) == []
    assert evaluator.assert_fact(_fact("login", "u1", now + timedelta(seconds=20))) == []


def test_outside_window_does_not_match():
    now = datetime.now(timezone.utc)
    evaluator = SequenceEvaluator(
        steps=[
            {"field": "event", "op": "==", "value": "login"},
            {"field": "event", "op": "==", "value": "purchase"},
        ],
        within_window_seconds=60,
        correlate_on=["user_id"],
    )

    evaluator.assert_fact(_fact("login", "u1", now))
    matches = evaluator.assert_fact(_fact("purchase", "u1", now + timedelta(seconds=61)))
    assert matches == []


def test_wrong_correlation_does_not_match():
    now = datetime.now(timezone.utc)
    evaluator = SequenceEvaluator(
        steps=[
            {"field": "event", "op": "==", "value": "login"},
            {"field": "event", "op": "==", "value": "purchase"},
        ],
        within_window_seconds=120,
        correlate_on=["user_id"],
    )

    evaluator.assert_fact(_fact("login", "u1", now))
    matches = evaluator.assert_fact(_fact("purchase", "u2", now + timedelta(seconds=20)))
    assert matches == []


def test_partial_sequence_does_not_emit_false_positive():
    now = datetime.now(timezone.utc)
    evaluator = SequenceEvaluator(
        steps=[
            {"field": "event", "op": "==", "value": "login"},
            {"field": "event", "op": "==", "value": "purchase"},
            {"field": "event", "op": "==", "value": "refund"},
        ],
        within_window_seconds=120,
        correlate_on=["user_id"],
    )

    assert evaluator.assert_facts(
        [
            _fact("login", "u1", now),
            _fact("purchase", "u1", now + timedelta(seconds=20)),
        ]
    ) == []
