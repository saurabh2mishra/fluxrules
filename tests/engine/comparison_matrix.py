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


# A path's answer for one fact: the ids of the rules that fired, or None when
# the path cannot take that fact (a JSON path given a Decimal, for example).
Answer = frozenset[int] | None


@dataclass(frozen=True)
class EvalPath:
    """One way of evaluating rules.

    ``run(cases, rules, config, facts)`` returns one :data:`Answer` per fact.
    ``supports(case)`` says whether the path can express a case at all; cases
    it cannot express are left out of the comparison for that path.
    """

    name: str
    run: Callable[[list[Case], list[Rule], EngineConfig, list[dict[str, Any]]], list[Answer]]
    supports: Callable[[Case], bool] = lambda case: True


def _engine_path(name: str, **options: Any) -> EvalPath:
    def run(cases, rules, config, facts):
        out: list[Answer] = []
        for fact in facts:
            # Streaming must see each fact first, so it gets a fresh engine.
            engine = PhreakEngine(config=config, **options)
            engine.load_rules(rules)
            out.append(frozenset(engine.evaluate(fact).fired_rules))
        return out

    return EvalPath(name, run)


def _batch_run(cases, rules, config, facts):
    engine = PhreakEngine(config=config)
    engine.load_rules(rules)
    return [frozenset(r.fired_rules) for r in engine.evaluate_batch(facts)]


def _evaluate_run(cases, rules, config, facts):
    with process_config(config):
        return [frozenset(evaluate(rules, fact).fired_rules) for fact in facts]


def _cross_fact_supports(case: Case) -> bool:
    # A pattern's constraints are a flat AND of field-op-value checks.
    return case.wrapper in ("plain", "AND")


def _cross_fact_run(cases, rules, config, facts):
    from fluxrules.engine.cross_fact import CrossFactEngine, CrossFactRule, Pattern

    cross_rules = []
    for case in cases:
        if not _cross_fact_supports(case):
            continue
        constraints = [(FIELD, case.op, case.value)]
        if case.wrapper == "AND":
            constraints.append(("always", "==", 1))
        cross_rules.append(
            CrossFactRule(
                id=case.rule_id,
                name=f"case_{case.rule_id}",
                patterns=[Pattern(var="f", fact_type="Fact", constraints=constraints)],
                action="hit",
            )
        )
    out: list[Answer] = []
    with process_config(config):  # the engine reads the process-wide config
        for fact in facts:
            engine = CrossFactEngine()
            engine.load_rules(cross_rules)
            engine.insert("Fact", fact)
            out.append(frozenset(a.rule_id for a in engine.activations()))
    return out


PATHS: dict[str, EvalPath] = {
    p.name: p
    for p in (
        _engine_path("engine"),
        _engine_path("engine, no prefilter", alpha_prefilter=False),
        _engine_path("engine, compiled", compile_conditions=True),
        _engine_path("engine, streaming", streaming_mode=True),
        EvalPath("evaluate_batch", _batch_run),
        EvalPath("fluxrules.evaluate()", _evaluate_run),
        EvalPath("CrossFactEngine", _cross_fact_run, _cross_fact_supports),
    )
}

# The path every other path is compared with.
REFERENCE_PATH = "engine, no prefilter"


# --- paths that take JSON: the CLI and the HTTP API ------------------------


def is_json_value(value: Any) -> bool:
    """True when *value* survives a JSON round trip unchanged."""
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(is_json_value(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and is_json_value(v) for k, v in value.items())
    return False


def _json_supports(case: Case) -> bool:
    return is_json_value(case.value)


def rule_document(cases: list[Case]) -> list[dict[str, Any]]:
    """The JSON-safe cases as rule mappings, with distinct priorities."""
    return [
        {
            "id": case.rule_id,
            "name": f"case_{case.rule_id}",
            "priority": case.rule_id,
            "action": "hit",
            "conditions": _wrap(case.wrapper, _leaf(case.op, case.value)),
        }
        for case in cases
        if _json_supports(case)
    ]


def _config_yaml(config: EngineConfig) -> str:
    lines = [
        f"strict_null_handling: {str(config.strict_null_handling).lower()}",
        f"strict_type_comparison: {str(config.strict_type_comparison).lower()}",
        f"boolean_string_coercion: {str(config.boolean_string_coercion).lower()}",
    ]
    if config.missing_field is not None:
        lines.append(f"missing_field: {config.missing_field}")
    return "\n".join(lines) + "\n"


def cli_path(workdir: Any) -> EvalPath:
    """``fluxrules evaluate rules.json fact.json --config fluxrules.yaml``.

    The settings go in the config file, the way a CLI user would set them.
    """
    import json

    from typer.testing import CliRunner

    from fluxrules.cli.main import app

    runner = CliRunner()

    def run(cases, rules, config, facts):
        rules_file = workdir / "rules.json"
        rules_file.write_text(json.dumps(rule_document(cases)))
        config_file = workdir / "fluxrules.yaml"
        config_file.write_text(_config_yaml(config))
        out: list[Answer] = []
        for i, fact in enumerate(facts):
            if not is_json_value(fact):
                out.append(None)
                continue
            fact_file = workdir / f"fact_{i}.json"
            fact_file.write_text(json.dumps(fact))
            result = runner.invoke(
                app,
                [
                    "evaluate",
                    str(rules_file),
                    str(fact_file),
                    "--format",
                    "json",
                    "--config",
                    str(config_file),
                ],
            )
            if result.exit_code != 0:
                raise AssertionError(f"fluxrules evaluate failed on {fact!r}: {result.output}")
            body = json.loads(result.stdout)
            out.append(frozenset(r["id"] for r in body["matched_rules"]))
        return out

    return EvalPath("CLI", run, _json_supports)


def http_path(client: Any, session_factory: Any) -> EvalPath:
    """Rules stored in the server's database, facts sent to /evaluate/bulk.

    Rules are written through the persistence mapper rather than
    ``POST /api/v1/rules``, which waits for Redis on every write; storage and
    the HTTP evaluation path are what this checks.
    """
    from fluxrules.persistence.mappers import domain_rule_to_orm

    group = "comparison_matrix"
    orm_id_to_case: dict[int, int] = {}

    def store(cases: list[Case]) -> None:
        with quiet():
            json_rules = [Rule(**doc) for doc in rule_document(cases)]
        db = session_factory()
        try:
            rows = [domain_rule_to_orm(rule, group=group) for rule in json_rules]
            for row, rule in zip(rows, json_rules, strict=True):
                row.priority = rule.priority
                db.add(row)
            db.commit()
            for row, rule in zip(rows, json_rules, strict=True):
                orm_id_to_case[row.id] = rule.id
        finally:
            db.close()

    def run(cases, rules, config, facts):
        if not orm_id_to_case:
            store(cases)
        sendable = [i for i, fact in enumerate(facts) if is_json_value(fact)]
        with process_config(config):  # the server runs in this process
            response = client.post(
                "/api/v1/evaluate/bulk",
                json={"facts": [facts[i] for i in sendable], "ruleset_id": group},
            )
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        out: list[Answer] = [None] * len(facts)
        for i, result in zip(sendable, results, strict=True):
            out[i] = frozenset(orm_id_to_case[rid] for rid in result["matched_rules"])
        return out

    return EvalPath("HTTP API", run, _json_supports)


@dataclass(frozen=True)
class Disagreement:
    config: str
    path: str
    fact: str
    case: str
    reference: bool
    got: bool


@dataclass
class MatrixResult:
    cases: list[Case]
    # (config label, fact label, rule id) -> did the reference path fire it
    reference: dict[tuple[str, str, int], bool]
    disagreements: list[Disagreement]
    # (path name, config label) -> number of (fact, case) answers compared
    compared: dict[tuple[str, str], int]


def run_matrix(
    configs: dict[str, EngineConfig] | None = None,
    extra_paths: list[EvalPath] | None = None,
) -> MatrixResult:
    """Evaluate every case on every path and compare each with the reference."""
    cases, rules = build_cases()
    facts = build_facts()
    fact_dicts = [fact for _, fact in facts]
    paths = {**PATHS, **{p.name: p for p in extra_paths or []}}
    reference_answers: dict[tuple[str, str, int], bool] = {}
    disagreements: list[Disagreement] = []
    compared: dict[tuple[str, str], int] = {}
    with quiet():
        for config_label, config in (configs or CONFIGS).items():
            results = {
                name: path.run(cases, rules, config, fact_dicts) for name, path in paths.items()
            }
            reference = results[REFERENCE_PATH]
            for (fact_label, _), ref in zip(facts, reference, strict=True):
                for case in cases:
                    reference_answers[(config_label, fact_label, case.rule_id)] = (
                        case.rule_id in ref
                    )
            for name, answers in results.items():
                supported = [c for c in cases if paths[name].supports(c)]
                count = 0
                for (fact_label, _), ref, got in zip(facts, reference, answers, strict=True):
                    if got is None:
                        continue
                    for case in supported:
                        count += 1
                        r, g = case.rule_id in ref, case.rule_id in got
                        if r != g:
                            disagreements.append(
                                Disagreement(config_label, name, fact_label, case.label, r, g)
                            )
                compared[(name, config_label)] = count
    return MatrixResult(cases, reference_answers, disagreements, compared)


# --- known disagreements ----------------------------------------------------

PREFILTERED_PATHS = frozenset({"engine", "engine, compiled", "engine, streaming", "evaluate_batch"})


@dataclass(frozen=True)
class Known:
    """A disagreement that happens today, the paths and settings it affects, and why.

    ``tests/engine/test_comparison_matrix.py`` requires every disagreement to
    match one of these and every one of these to still happen. The reference
    page lists them under "Known differences between paths".
    """

    title: str
    paths: str
    settings: str
    reason: str
    matches: Callable[[Disagreement], bool]


# Empty: every path agrees under every setting. Add an entry, with its cause,
# only for a disagreement that is known and accepted for now.
KNOWN: list[Known] = []
