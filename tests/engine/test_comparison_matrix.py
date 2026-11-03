"""Every evaluation path gives the same answer for every comparison case.

``comparison_matrix`` evaluates each operator against each kind of value
(numbers, Decimal, booleans, strings, None, NaN, dates, lists, a missing
field), plain and wrapped in NOT, AND and OR, under each comparison setting,
on every in-process path. This test compares every path with
``engine, no prefilter``.

Known disagreements are listed in ``KNOWN`` with the bug behind them. The test
fails on a disagreement that is not listed, and on a listed one that no longer
happens, so the list stays exact: when a bug is fixed, remove its entry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from tests.engine.comparison_matrix import (
    CONFIGS,
    PATHS,
    REFERENCE_PATH,
    Disagreement,
    build_cases,
    build_facts,
    run_matrix,
)

PREFILTERED_PATHS = {"engine", "engine, compiled", "engine, streaming", "evaluate_batch"}


@dataclass(frozen=True)
class Known:
    reason: str
    matches: Callable[[Disagreement], bool]


KNOWN = [
    Known(
        "The alpha prefilter ignores boolean_string_coercion, so it drops "
        "'== True' and 'in [True]' rules for the string 'true' before the "
        "operator converts it. OR rules are kept as candidates, so they agree.",
        lambda d: (
            d.config == "boolean_string_coercion"
            and d.path in PREFILTERED_PATHS
            and d.fact == "str 'true'"
            and d.case
            in {"v == bool True", "AND(v == bool True)", "v in [True]", "AND(v in [True])"}
        ),
    ),
    Known(
        "fluxrules.evaluate() runs on the reference evaluator, which never "
        "reads strict_null_handling, strict_type_comparison or "
        "boolean_string_coercion.",
        lambda d: (
            d.path == "fluxrules.evaluate()"
            and d.config
            in {"strict_null_handling", "strict_type_comparison", "boolean_string_coercion"}
        ),
    ),
]


@pytest.fixture(scope="module")
def disagreements() -> list[Disagreement]:
    return run_matrix()[1]


def test_the_matrix_covers_every_path_setting_and_operator():
    from fluxrules.engine.operators import VALID_OPERATORS

    cases, _ = build_cases()
    word_aliases = {"eq", "ne", "gt", "gte", "lt", "lte"}  # normalised to symbols first
    assert {c.op for c in cases} == VALID_OPERATORS - word_aliases
    assert REFERENCE_PATH in PATHS
    assert len(PATHS) >= 6 and len(CONFIGS) >= 6
    assert len(build_facts()) >= 19


def test_no_unlisted_disagreement(disagreements):
    unlisted = [d for d in disagreements if not any(k.matches(d) for k in KNOWN)]
    report = "\n".join(
        f"  [{d.config}] {d.path}: {d.case} on fact {d.fact}: reference={d.reference}, got={d.got}"
        for d in unlisted[:40]
    )
    assert not unlisted, f"{len(unlisted)} paths disagree with {REFERENCE_PATH!r}:\n{report}"


@pytest.mark.parametrize("known", KNOWN, ids=[k.reason[:60] for k in KNOWN])
def test_every_listed_disagreement_still_happens(known, disagreements):
    assert any(known.matches(d) for d in disagreements), (
        "This disagreement no longer happens. Remove it from KNOWN: " + known.reason
    )
