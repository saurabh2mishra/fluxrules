"""Every operator x value type x setting, evaluated on every in-process path.

Each setting builds one rule set holding a rule per (operator, rule value,
wrapper) case, so a path evaluates every case in one call per fact. A path's
answer for a fact is an :class:`Outcome`: the rule ids that fired, the
comparisons that could not be made, and whether the evaluation raised. Two
paths agree when their outcomes are equal.
``tests/engine/test_comparison_matrix.py`` asserts the paths agree, and
``tests/engine/comparison_page.py`` renders what they answer.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fluxrules import Rule, evaluate
from fluxrules.domain.comparison_issues import ComparisonIssue
from fluxrules.domain.errors import (
    ComparisonWarning,
    MembershipValueWarning,
    MissingFieldNotWarning,
    UncomparableValuesError,
)
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
    "Decimal NaN": Decimal("NaN"),
    "inf": math.inf,
    "date": date(2026, 6, 1),
    "datetime": datetime(2026, 6, 1, 12, 0),
    "ISO date str": "2026-06-01",
    "list [5]": [5],
    "tuple (5,)": (5,),
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
    # Unhashable members: the prefilter cannot put them in a set.
    "[{'a': 5}, [5]]": [{"a": 5}, [5]],
    "{'a': 5} (single)": {"a": 5},
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
    "uncomparable=unknown": EngineConfig(uncomparable="unknown"),
    "uncomparable=false": EngineConfig(uncomparable="false"),
    "uncomparable=raise": EngineConfig(uncomparable="raise"),
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
        warnings.simplefilter("ignore", ComparisonWarning)
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


@dataclass(frozen=True)
class Outcome:
    """What a path answered for one fact."""

    fired: frozenset[int] = frozenset()
    # The comparisons that could not be made, or None when the path does not
    # list them (CrossFactEngine).
    issues: frozenset[ComparisonIssue] | None = None
    # The evaluation raised UncomparableValuesError (uncomparable="raise").
    raised: bool = False


# A path's answer for one fact, or None when the path cannot take that fact
# (a JSON path given a Decimal, for example).
Answer = Outcome | None


def outcome_of(result: Any) -> Outcome:
    """The :class:`Outcome` of an ``EvaluationResult``."""
    return Outcome(frozenset(result.fired_rules), frozenset(result.comparison_issues))


def evaluated(run: Callable[[], Any]) -> Outcome:
    """Run one evaluation; an ``UncomparableValuesError`` is a raised outcome."""
    try:
        return outcome_of(run())
    except UncomparableValuesError:
        return Outcome(raised=True)


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
            out.append(evaluated(lambda: engine.evaluate(fact)))  # noqa: B023
        return out

    return EvalPath(name, run)


def _batch_path(name: str, workers: int | None) -> EvalPath:
    def run(cases, rules, config, facts):
        engine = PhreakEngine(config=config)
        engine.load_rules(rules)
        if config.uncomparable == "raise":
            # A batch stops at its first error, so each fact gets its own call.
            # One fact runs in this process even with workers; that workers
            # pass the error back is tested in tests/unit/test_uncomparable.py.
            return [
                evaluated(lambda: engine.evaluate_batch([fact], workers=workers)[0])  # noqa: B023
                for fact in facts
            ]
        return [outcome_of(r) for r in engine.evaluate_batch(facts, workers=workers)]

    return EvalPath(name, run)


# --- the same rules written another way -------------------------------------

_F_METHODS = {
    "in": "isin",
    "not_in": "not_in",
    "contains": "contains",
    "not_contains": "not_contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
    "regex": "regex",
}


def f_condition(case: Case) -> Any:
    """The case as an ``F`` expression, the way an author writes it in Python."""
    from fluxrules import F
    from fluxrules.engine.operators import COMPARISONS

    field = F(FIELD)
    if case.op in COMPARISONS:
        leaf = COMPARISONS[case.op](field, case.value)
    else:
        leaf = getattr(field, _F_METHODS[case.op])(case.value)
    if case.wrapper == "NOT":
        return ~leaf
    if case.wrapper == "AND":
        return leaf & (F("always") == 1)
    if case.wrapper == "OR":
        return leaf | (F("always") == 0)
    return leaf


def _f_run(cases, rules, config, facts):
    with quiet():
        f_rules = [
            Rule(id=c.rule_id, name=f"case_{c.rule_id}", conditions=f_condition(c), action="hit")
            for c in cases
        ]
    return _engine_path("", alpha_prefilter=False).run(cases, f_rules, config, facts)


def is_yaml_value(value: Any) -> bool:
    """True when *value* survives a YAML round trip with the same type."""
    if value is None or isinstance(value, (bool, int, float, str, date)):
        return True
    if isinstance(value, list):
        return all(is_yaml_value(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and is_yaml_value(v) for k, v in value.items())
    return False


def _yaml_supports(case: Case) -> bool:
    return is_yaml_value(case.value)


def yaml_path(workdir: Any) -> EvalPath:
    """Rules written to a YAML file and read back with ``load_rules_from_yaml``."""
    import yaml

    from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml

    def run(cases, rules, config, facts):
        document = [
            {
                "id": c.rule_id,
                "name": f"case_{c.rule_id}",
                "action": "hit",
                "conditions": _wrap(c.wrapper, _leaf(c.op, c.value)),
            }
            for c in cases
            if _yaml_supports(c)
        ]
        path = workdir / "rules.yaml"
        path.write_text(yaml.safe_dump(document, sort_keys=False))
        with quiet():
            loaded = [Rule(**data) for data in load_rules_from_yaml(str(path))]
        return _engine_path("", alpha_prefilter=False).run(cases, loaded, config, facts)

    return EvalPath("YAML rule file", run, _yaml_supports)


def _evaluate_run(cases, rules, config, facts):
    with process_config(config):
        return [evaluated(lambda: evaluate(rules, fact)) for fact in facts]  # noqa: B023


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
            try:
                engine.insert("Fact", fact)
            except UncomparableValuesError:
                out.append(Outcome(raised=True))
                continue
            # CrossFactEngine warns and raises, but does not list issues.
            out.append(Outcome(frozenset(a.rule_id for a in engine.activations())))
    return out


def _sql_prefilter_run(cases, rules, config, facts):
    """PreFilteredEvaluator over an in-memory SQLite fact store, one fact at a time."""
    from sqlalchemy import create_engine

    from fluxrules.prefilter import PreFilteredEvaluator
    from fluxrules.prefilter.sql_store import FactPreFilterStore

    engine = PhreakEngine(config=config)
    engine.load_rules(rules)
    out: list[Answer] = []
    for fact in facts:
        store = FactPreFilterStore(engine=create_engine("sqlite://"))
        try:
            results, stats = PreFilteredEvaluator(engine, store).run([fact])
        except UncomparableValuesError:
            out.append(Outcome(raised=True))
            continue
        finally:
            store.dispose()
        if results:
            out.append(outcome_of(results[0]))
        elif stats.candidate_facts == 0 and config.uncomparable == "raise":
            # Screened out, so never evaluated: it cannot raise.
            out.append(None)
        else:
            # run() returns only facts that fired, so their issues are unknown.
            out.append(Outcome(frozenset()))
    return out


PATHS: dict[str, EvalPath] = {
    p.name: p
    for p in (
        _engine_path("engine"),
        _engine_path("engine, no prefilter", alpha_prefilter=False),
        _engine_path("engine, compiled", compile_conditions=True),
        _engine_path("engine, streaming", streaming_mode=True),
        _batch_path("evaluate_batch", workers=None),
        _batch_path("evaluate_batch(workers=2)", workers=2),
        EvalPath("fluxrules.evaluate()", _evaluate_run),
        EvalPath("rules written with F", _f_run),
        EvalPath("CrossFactEngine", _cross_fact_run, _cross_fact_supports),
        EvalPath("PreFilteredEvaluator (SQLite)", _sql_prefilter_run),
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
    if config.uncomparable is not None:
        lines.append(f"uncomparable: {config.uncomparable}")
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
            if result.exit_code == 1 and "Cannot compare" in result.output:
                out.append(Outcome(raised=True))
                continue
            if result.exit_code != 0:
                raise AssertionError(f"fluxrules evaluate failed on {fact!r}: {result.output}")
            body = json.loads(result.stdout)
            out.append(
                Outcome(
                    frozenset(r["id"] for r in body["matched_rules"]),
                    frozenset(ComparisonIssue(**i) for i in body["comparison_issues"]),
                )
            )
        return out

    return EvalPath("CLI", run, _json_supports)


def http_path(client: Any, session_factory: Any) -> EvalPath:
    """Rules stored in the server's database, facts sent to /evaluate/bulk.

    Rules are written through the persistence mapper rather than
    ``POST /api/v1/rules``, which waits for Redis on every write; storage and
    the HTTP evaluation path are what this checks.
    """
    from fluxrules.persistence.mappers import domain_rule_to_orm

    # One stored ruleset per set of cases the matrix sends.
    rulesets: dict[frozenset[int], str] = {}
    orm_id_to_case: dict[int, int] = {}

    def store(cases: list[Case], group: str) -> None:
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

    def outcome(result: dict[str, Any]) -> Outcome:
        return Outcome(
            frozenset(orm_id_to_case[rid] for rid in result["matched_rules"]),
            frozenset(ComparisonIssue(**i) for i in result["comparison_issues"]),
        )

    def run(cases, rules, config, facts):
        ids = frozenset(c.rule_id for c in cases)
        if ids not in rulesets:
            rulesets[ids] = f"comparison_matrix_{len(rulesets)}"
            store(cases, rulesets[ids])
        group = rulesets[ids]

        def post(fact_list: list[dict[str, Any]]) -> Any:
            return client.post(
                "/api/v1/evaluate/bulk", json={"facts": fact_list, "ruleset_id": group}
            )

        sendable = [i for i, fact in enumerate(facts) if is_json_value(fact)]
        out: list[Answer] = [None] * len(facts)
        with process_config(config):  # the server runs in this process
            if config.uncomparable == "raise":
                # The request fails at the first fact that raises, so send
                # each fact on its own.
                for i in sendable:
                    response = post([facts[i]])
                    if response.status_code == 422:
                        assert response.json()["error"] == "UNCOMPARABLE_VALUES"
                        out[i] = Outcome(raised=True)
                    else:
                        assert response.status_code == 200, response.text
                        out[i] = outcome(response.json()["results"][0])
                return out
            response = post([facts[i] for i in sendable])
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        for i, result in zip(sendable, results, strict=True):
            out[i] = outcome(result)
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
    detail: str = ""


@dataclass
class MatrixResult:
    cases: list[Case]
    # (config label, fact label, rule id) -> did the reference path fire it
    reference: dict[tuple[str, str, int], bool]
    disagreements: list[Disagreement]
    # (path name, config label) -> number of (fact, case) answers compared
    compared: dict[tuple[str, str], int]
    # (config label, fact label) -> the reference path's comparison issues
    issues: dict[tuple[str, str], frozenset[ComparisonIssue]] = field(default_factory=dict)
    # (config label, fact label) -> did the reference path raise
    raised: dict[tuple[str, str], bool] = field(default_factory=dict)


def _describe_issues(issues: frozenset[ComparisonIssue] | None) -> str:
    if not issues:
        return "none"
    return "; ".join(
        sorted(f"{i.operator} {i.fact_type}/{i.rule_type}: {i.reason}" for i in issues)
    )


def run_matrix(
    configs: dict[str, EngineConfig] | None = None,
    extra_paths: list[EvalPath] | None = None,
) -> MatrixResult:
    """Evaluate every case on every path and compare each with the reference.

    A path is compared on the rules that fired for each case it supports, on
    whether it raised, and, when it lists them, on its comparison issues. A
    path that supports only some cases is compared with the reference path
    run on those cases alone, since issues are per evaluation, not per rule.

    Each wrapper (plain, NOT, AND, OR) is evaluated on its own. In one engine
    the NOT rule, which the alpha prefilter never skips, reports the same issue
    as its plain twin, and so would hide a prefilter that wrongly skips the
    plain rule.
    """
    cases, rules = build_cases()
    rules_by_id = {rule.id: rule for rule in rules}
    facts = build_facts()
    paths = {**PATHS, **{p.name: p for p in extra_paths or []}}
    result = MatrixResult(cases, {}, [], {})
    with quiet():
        for config_label, config in (configs or CONFIGS).items():
            for wrapper in WRAPPERS:
                group = [c for c in cases if c.wrapper == wrapper]
                group_rules = [rules_by_id[c.rule_id] for c in group]
                _compare_group(
                    result, paths, config_label, config, wrapper, group, group_rules, facts
                )
    return result


def _compare_group(
    result: MatrixResult,
    paths: dict[str, EvalPath],
    config_label: str,
    config: EngineConfig,
    wrapper: str,
    cases: list[Case],
    rules: list[Rule],
    facts: list[tuple[str, dict[str, Any]]],
) -> None:
    """Run the cases of one wrapper on every path and record what differs."""
    fact_dicts = [fact for _, fact in facts]
    reference_path = paths[REFERENCE_PATH]
    supported_by = {name: [c for c in cases if path.supports(c)] for name, path in paths.items()}
    answers = {
        name: path.run(cases, rules, config, fact_dicts)
        for name, path in paths.items()
        if supported_by[name]
    }
    reference = answers[REFERENCE_PATH]
    for (fact_label, _), ref in zip(facts, reference, strict=True):
        assert ref is not None
        key = (config_label, fact_label)
        result.issues[key] = result.issues.get(key, frozenset()) | (ref.issues or frozenset())
        result.raised[key] = result.raised.get(key, False) or ref.raised
        for case in cases:
            result.reference[(config_label, fact_label, case.rule_id)] = case.rule_id in ref.fired
    # The reference run on a subset of cases, for paths that take only some.
    subset_reference: dict[frozenset[int], list[Answer]] = {}
    for name, got_answers in answers.items():
        supported = supported_by[name]
        ids = frozenset(c.rule_id for c in supported)
        if len(supported) == len(cases):
            issue_reference = reference
        else:
            if ids not in subset_reference:
                subset_rules = [r for r in rules if r.id in ids]
                subset_reference[ids] = reference_path.run(
                    supported, subset_rules, config, fact_dicts
                )
            issue_reference = subset_reference[ids]
        count = 0
        for (fact_label, _), ref, sub, got in zip(
            facts, reference, issue_reference, got_answers, strict=True
        ):
            if got is None:
                continue
            assert ref is not None and sub is not None
            count += 1
            if sub.raised != got.raised:
                result.disagreements.append(
                    Disagreement(
                        config_label,
                        name,
                        fact_label,
                        f"(raised, {wrapper})",
                        sub.raised,
                        got.raised,
                    )
                )
                continue
            if got.raised:
                continue
            if got.issues is not None and got.issues != sub.issues:
                result.disagreements.append(
                    Disagreement(
                        config_label,
                        name,
                        fact_label,
                        f"(comparison issues, {wrapper})",
                        True,
                        False,
                        f"reference: {_describe_issues(sub.issues)}; "
                        f"got: {_describe_issues(got.issues)}",
                    )
                )
            for case in supported:
                count += 1
                r, g = case.rule_id in ref.fired, case.rule_id in got.fired
                if r != g:
                    result.disagreements.append(
                        Disagreement(config_label, name, fact_label, case.label, r, g)
                    )
        key = (name, config_label)
        result.compared[key] = result.compared.get(key, 0) + count


# --- known disagreements ----------------------------------------------------

PREFILTERED_PATHS = frozenset(
    {
        "engine",
        "engine, compiled",
        "engine, streaming",
        "evaluate_batch",
        "evaluate_batch(workers=2)",
    }
)


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
