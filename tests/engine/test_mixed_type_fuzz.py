"""Random nested rules over mixed value types, under random settings.

``test_differential_fuzz`` proves the paths agree for numeric rules under the
default settings. This test widens it: rule and fact values come from the
same mixed pool as the comparison matrix (numbers, Decimal, booleans, numeric
and plain strings, None, NaN, inf, dates, lists, missing fields), every
operator is used, trees nest AND / OR / NOT several levels deep over three
fields, and each rule set runs under a random combination of comparison
settings. Every in-process path that can express a tree is compared with
``engine, no prefilter``.

The matrix pins each known bug exactly. Here a bug can surface anywhere in a
tree, so the comparisons it would break are skipped instead (see
``_skipped_paths``); remove a skip when its bug is fixed.

Every rule set is seeded. Set ``FLUXRULES_FUZZ_EXAMPLES`` for a deeper run.
"""

from __future__ import annotations

import os
import random
from typing import Any

import pytest
from tests.engine.comparison_matrix import (
    FACT_VALUES,
    MISSING,
    OPERATOR_VALUES,
    PATHS,
    PREFILTERED_PATHS,
    REFERENCE_PATH,
    quiet,
)

from fluxrules import Rule
from fluxrules.engine.configuration import EngineConfig

FIELDS = ("f0", "f1", "f2")
RULES_PER_SET = 8
FACTS_PER_SET = 6
EXAMPLES = int(os.environ.get("FLUXRULES_FUZZ_EXAMPLES", "60"))
# CrossFactEngine has no OR or NOT, so it cannot express a random tree.
TREE_PATHS = {name: path for name, path in PATHS.items() if name != "CrossFactEngine"}


def _random_config(rng: random.Random) -> EngineConfig:
    return EngineConfig(
        strict_null_handling=rng.random() < 0.3,
        strict_type_comparison=rng.random() < 0.3,
        boolean_string_coercion=rng.random() < 0.3,
        missing_field=rng.choice([None, "false", "unknown"]),
    )


def _random_leaf(rng: random.Random) -> dict[str, Any]:
    op = rng.choice(list(OPERATOR_VALUES))
    value = rng.choice(list(OPERATOR_VALUES[op].values()))
    return {"type": "condition", "field": rng.choice(FIELDS), "op": op, "value": value}


def _random_tree(rng: random.Random, depth: int) -> dict[str, Any]:
    if depth == 0 or rng.random() < 0.35:
        return _random_leaf(rng)
    kind = rng.choice(["AND", "OR", "NOT"])
    if kind == "NOT":
        return {"type": "not", "condition": _random_tree(rng, depth - 1)}
    children = [_random_tree(rng, depth - 1) for _ in range(rng.randint(2, 3))]
    return {"type": "group", "op": kind, "children": children}


def _random_fact(rng: random.Random) -> dict[str, Any]:
    fact = {}
    for field in FIELDS:
        value = rng.choice(list(FACT_VALUES.values()))
        if value is not MISSING:
            fact[field] = value
    return fact


def _skipped_paths(config: EngineConfig) -> set[str]:
    """Comparisons a known bug breaks; see ``comparison_matrix.KNOWN``."""
    skipped = set()
    if config.boolean_string_coercion:
        # The alpha prefilter ignores boolean_string_coercion.
        skipped.update(PREFILTERED_PATHS)
    if (
        config.strict_null_handling
        or config.strict_type_comparison
        or config.boolean_string_coercion
    ):
        # fluxrules.evaluate() ignores the three comparison flags.
        skipped.add("fluxrules.evaluate()")
    return skipped


@pytest.mark.parametrize("seed", range(EXAMPLES))
def test_paths_agree_on_random_mixed_type_rules(seed):
    rng = random.Random(seed)
    config = _random_config(rng)
    with quiet():
        rules = [
            Rule(id=i + 1, name=f"r{i + 1}", conditions=_random_tree(rng, 3), action="hit")
            for i in range(RULES_PER_SET)
        ]
    facts = [_random_fact(rng) for _ in range(FACTS_PER_SET)]
    skipped = _skipped_paths(config)

    with quiet():
        reference = TREE_PATHS[REFERENCE_PATH].run([], rules, config, facts)
        for name, path in TREE_PATHS.items():
            if name == REFERENCE_PATH or name in skipped:
                continue
            answers = path.run([], rules, config, facts)
            for fact, ref, got in zip(facts, reference, answers, strict=True):
                if ref != got:
                    differing = sorted(ref ^ got)
                    pytest.fail(
                        f"seed {seed}: {name!r} fired {sorted(got)}, {REFERENCE_PATH!r} "
                        f"fired {sorted(ref)}\n  config: {config}\n  fact: {fact!r}\n"
                        + "\n".join(
                            f"  rule {rid}: {rules[rid - 1].conditions}" for rid in differing
                        )
                    )
