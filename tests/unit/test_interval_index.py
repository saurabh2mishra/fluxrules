from __future__ import annotations

from fluxrules.services.validation._interval_index import IntervalIndex
from fluxrules.services.validation._normalization import Interval


def test_remove_drops_rule_from_every_field_and_keeps_order() -> None:
    index = IntervalIndex()
    index.bulk_build(
        [
            ("a", "age", Interval(0, 10, True, True)),
            ("b", "age", Interval(5, 20, True, True)),
            ("c", "age", Interval(15, 30, True, True)),
            ("b", "score", Interval(0, 100, True, True)),
        ]
    )

    index.remove("b")

    assert len(index) == 2
    assert index.query_overlapping_set("age", Interval(0, 30, True, True)) == {"a", "c"}
    assert index.query_overlapping_set("score", Interval(0, 100, True, True)) == set()
    # Re-adding after removal still bisects into the right slot.
    index.add("d", "age", Interval(12, 13, True, True))
    assert index.query_overlapping_set("age", Interval(11, 14, True, True)) == {"d"}
