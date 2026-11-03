"""Every operator x value type x setting, evaluated on every in-process path.

Each setting builds one rule set holding a rule per (operator, rule value,
wrapper) case, so a path evaluates every case in one call per fact. A path's
answer for a fact is the set of rule ids that fired; two paths agree when the
sets are equal. ``tests/engine/test_comparison_matrix.py`` asserts the paths
agree, and ``scripts/comparison_table.py`` prints what they answer.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fluxrules import Rule, evaluate
from fluxrules.domain.errors import MembershipValueWarning, MissingFieldNotWarning
from fluxrules.engine.configuration import EngineConfig, get_config, set_config
from fluxrules.engine.phreak import PhreakEngine

FIELD = "v"
MISSING = "<missing>"

# Fact values, by label. MISSING means the field is absent from the fact.
FACT_VALUES: dict[str, Any] = {
    "int 5": 5,
    "int 0": 0,
    "float 5.5": 5.5,
    "Decimal 5.5": Decimal("5.5"),
    "bool True": True,
    "bool False": False,
    "str '5'": "5",
    "str 'true'": "true",
    "str 'abc'": "abc",
    "str ''": "",
    "None": None,
    "NaN": math.nan,
    "inf": math.inf,
    "date": date(2026, 6, 1),
    "datetime": datetime(2026, 6, 1, 12, 0),
    "ISO date str": "2026-06-01",
    "list [5]": [5],
    "dict": {"a": 5},
    "missing": MISSING,
}

# Rule values tested with each operator, by label.
ORDERED_RULE_VALUES: dict[str, Any] = {
    "int 5": 5,
    "float 5.5": 5.5,
    "str '5'": "5",
    "str 'abc'": "abc",
    "bool True": True,
    "date": date(2026, 1, 1),
    "None": None,
}
MEMBERSHIP_RULE_VALUES: dict[str, Any] = {
    "[5, 'abc']": [5, "abc"],
    "[True]": [True],
    "[None]": [None],
    "'abc' (single)": "abc",
}
TEXT_RULE_VALUES: dict[str, Any] = {"'a'": "a", "'5'": "5", "'('": "("}

OPERATOR_VALUES: dict[str, dict[str, Any]] = {
    **dict.fromkeys(("==", "!=", ">", ">=", "<", "<="), ORDERED_RULE_VALUES),
    "in": MEMBERSHIP_RULE_VALUES,
    "not_in": MEMBERSHIP_RULE_VALUES,
    **dict.fromkeys(
        ("contains", "not_contains", "starts_with", "ends_with", "regex"), TEXT_RULE_VALUES
    ),
}

# Settings, by label.
CONFIGS: dict[str, EngineConfig] = {
    "default": EngineConfig(),
    "strict_null_handling": EngineConfig(strict_null_handling=True),
    "strict_type_comparison": EngineConfig(strict_type_comparison=True),
    "boolean_string_coercion": EngineConfig(boolean_string_coercion=True),
    "missing_field=unknown": EngineConfig(missing_field="unknown"),
    "missing_field=false": EngineConfig(missing_field="false"),
}

WRAPPERS = ("plain", "NOT", "AND", "OR")


@dataclass(frozen=True)
class Case:
    """One rule: an operator and a rule value, possibly wrapped."""

    rule_id: int
    op: str
    value_label: str
    value: Any
    wrapper: str

    @property
    def label(self) -> str:
        inner = f"{FIELD} {self.op} {self.value_label}"
        return inner if self.wrapper == "plain" else f"{self.wrapper}({inner})"


def _leaf(op: str, value: Any) -> dict[str, Any]:
    return {"type": "condition", "field": FIELD, "op": op, "value": value}


# A second field that every fact has, so AND / OR wrappers test only the leaf.
_ALWAYS = {"type": "condition", "field": "always", "op": "==", "value": 1}
_NEVER = {"type": "condition", "field": "always", "op": "==", "value": 0}


def _wrap(wrapper: str, leaf: dict[str, Any]) -> dict[str, Any]:
    if wrapper == "NOT":
        return {"type": "not", "condition": leaf}
    if wrapper == "AND":
        return {"type": "group", "op": "AND", "children": [leaf, _ALWAYS]}
    if wrapper == "OR":
        return {"type": "group", "op": "OR", "children": [leaf, _NEVER]}
    return leaf


def build_cases() -> tuple[list[Case], list[Rule]]:
    """Every (operator, rule value, wrapper) case, with its rule."""
    cases: list[Case] = []
    rules: list[Rule] = []
    rule_id = 0
    with quiet():
        for op, values in OPERATOR_VALUES.items():
            for value_label, value in values.items():
                for wrapper in WRAPPERS:
                    rule_id += 1
                    case = Case(rule_id, op, value_label, value, wrapper)
                    rule = Rule(
                        id=rule_id,
                        name=f"case_{rule_id}",
                        conditions=_wrap(wrapper, _leaf(op, value)),
                        action="hit",
                    )
                    cases.append(case)
                    rules.append(rule)
    return cases, rules


def build_facts() -> list[tuple[str, dict[str, Any]]]:
    facts = []
    for label, value in FACT_VALUES.items():
        fact: dict[str, Any] = {"always": 1}
        if value is not MISSING:
            fact[FIELD] = value
        facts.append((label, fact))
    return facts


@contextmanager
def quiet() -> Iterator[None]:
    """Silence the warnings that only report on purpose-made cases."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", MembershipValueWarning)
        warnings.simplefilter("ignore", MissingFieldNotWarning)
        yield


@contextmanager
def process_config(config: EngineConfig) -> Iterator[None]:
    """Install *config* process-wide, for paths that read the global one."""
    old = get_config()
    set_config(config)
    try:
        yield
    finally:
        set_config(old)


Path = Callable[[list[Rule], EngineConfig, list[dict[str, Any]]], list[frozenset[int]]]


def _engine_path(**options: Any) -> Path:
    def run(rules: list[Rule], config: EngineConfig, facts: list[dict[str, Any]]):
        out = []
        for fact in facts:
            # Streaming must see each fact first, so it gets a fresh engine.
            engine = PhreakEngine(config=config, **options)
            engine.load_rules(rules)
            out.append(frozenset(engine.evaluate(fact).fired_rules))
        return out

    return run


def _batch_path(rules, config, facts):
    engine = PhreakEngine(config=config)
    engine.load_rules(rules)
    return [frozenset(r.fired_rules) for r in engine.evaluate_batch(facts)]


def _evaluate_path(rules, config, facts):
    with process_config(config):
        return [frozenset(evaluate(rules, fact).fired_rules) for fact in facts]


PATHS: dict[str, Path] = {
    "engine": _engine_path(),
    "engine, no prefilter": _engine_path(alpha_prefilter=False),
    "engine, compiled": _engine_path(compile_conditions=True),
    "engine, streaming": _engine_path(streaming_mode=True),
    "evaluate_batch": _batch_path,
    "fluxrules.evaluate()": _evaluate_path,
}

# The path every other path is compared with.
REFERENCE_PATH = "engine, no prefilter"


@dataclass(frozen=True)
class Disagreement:
    config: str
    path: str
    fact: str
    case: str
    reference: bool
    got: bool


def run_matrix(
    configs: dict[str, EngineConfig] | None = None,
) -> tuple[dict[tuple[str, str, str, int], bool], list[Disagreement], list[Case]]:
    """Evaluate every case on every path.

    Returns the reference answers keyed by (config, path, fact, rule id), the
    disagreements with the reference path, and the cases.
    """
    cases, rules = build_cases()
    facts = build_facts()
    fact_dicts = [fact for _, fact in facts]
    answers: dict[tuple[str, str, str, int], bool] = {}
    disagreements: list[Disagreement] = []
    with quiet():
        for config_label, config in (configs or CONFIGS).items():
            results = {name: path(rules, config, fact_dicts) for name, path in PATHS.items()}
            reference = results[REFERENCE_PATH]
            for name, fired in results.items():
                for (fact_label, _), ref, got in zip(facts, reference, fired, strict=True):
                    for case in cases:
                        r, g = case.rule_id in ref, case.rule_id in got
                        answers[(config_label, name, fact_label, case.rule_id)] = g
                        if r != g:
                            disagreements.append(
                                Disagreement(config_label, name, fact_label, case.label, r, g)
                            )
    return answers, disagreements, cases
