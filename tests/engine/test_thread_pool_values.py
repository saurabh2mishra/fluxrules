"""The thread pool evaluates facts whose values cannot be hashed.

With more candidate rules than ``parallel_threshold``, rules run in a thread
pool. It used to key a cache by the fact's values, so a list, dict or
bytearray value raised ``TypeError: unhashable type``.
"""

from __future__ import annotations

import warnings

import pytest

from fluxrules import F, Rule
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.phreak import PhreakEngine

RULES = [
    Rule(id=1, name="vip", conditions=F("tags").contains("vip"), action="a"),
    Rule(id=2, name="eu", conditions=F("address") == {"region": "eu"}, action="a"),
    Rule(id=3, name="small", conditions=~(F("blob") > 5), action="a"),
    Rule(id=4, name="big", conditions=F("amount") > 100, action="a"),
]


def _fired(fact: dict, *, threshold: int) -> list[int]:
    engine = PhreakEngine(config=EngineConfig(parallel_threshold=threshold))
    engine.load_rules(RULES)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sorted(engine.evaluate(fact).fired_rules)


@pytest.mark.parametrize(
    "fact",
    [
        {"tags": ["vip", "new"], "amount": 150},
        {"address": {"region": "eu"}},
        {"blob": bytearray(b"a"), "amount": 5},
        {"tags": [], "address": {}, "blob": bytearray(), "amount": 500},
    ],
)
def test_the_thread_pool_answers_as_the_sequential_path(fact):
    assert _fired(fact, threshold=0) == _fired(fact, threshold=10_000)
