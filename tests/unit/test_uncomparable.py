"""Comparisons that cannot be made: ``EngineConfig.uncomparable``.

``"abc" > 5``, ``None > 5``, ``NaN > 5``, a ``date`` against a ``datetime``,
``contains`` on a number and an invalid regex have no answer. The condition is
no match; the issue is listed in ``comparison_issues`` when it leaves the rule
undecided, and the setting chooses whether it also warns, makes ``NOT`` over
it unknown, or raises. ``tests/engine/test_comparison_matrix.py`` checks that
every evaluation path agrees; these tests pin each behaviour on its own.
"""

from __future__ import annotations

import json
import math
import pickle
import warnings
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from fluxrules import F, Rule, evaluate
from fluxrules.domain.comparison_issues import ComparisonIssue
from fluxrules.domain.errors import ComparisonWarning, UncomparableValuesError
from fluxrules.engine.configuration import EngineConfig, get_config, set_config
from fluxrules.engine.operators import compare_operator, evaluate_operator
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.engine.uncomparable import Uncomparable, reset_warnings


@pytest.fixture(autouse=True)
def fresh_warnings():
    """Each test sees each warning once, whatever ran before it."""
    reset_warnings()
    yield
    reset_warnings()


@pytest.fixture
def process_config():
    old = get_config()
    yield set_config
    set_config(old)


def _rule(rule_id, condition):
    return Rule(id=rule_id, name=f"r{rule_id}", conditions=condition, action="hit")


def _engine(*rules, **config):
    engine = PhreakEngine(config=EngineConfig(**config))
    engine.load_rules(list(rules))
    return engine


def _keys(result):
    return {(i.field, i.operator, i.fact_type, i.rule_type) for i in result.comparison_issues}


_PLAIN = {
    "field_present": True,
    "strict_null_handling": False,
    "strict_type_comparison": False,
    "boolean_string_coercion": False,
    "field": "v",
}


class TestWhatCannotBeCompared:
    @pytest.mark.parametrize(
        ("op", "fact", "rule", "reason"),
        [
            (">", "abc", 5, "these types cannot be ordered"),
            (">", None, 5, "None cannot be ordered"),
            ("<", 5, None, "None cannot be ordered"),
            (">", math.nan, 5, "NaN cannot be ordered"),
            (">=", Decimal("NaN"), 5, "NaN cannot be ordered"),
            ("<", 5, math.nan, "NaN cannot be ordered"),
            (">", datetime(2026, 1, 1), date(2026, 1, 1), "these types cannot be ordered"),
            ("contains", 5, "a", "the fact value cannot contain the rule value"),
            ("regex", "abc", "(", "the rule value is not a valid regular expression"),
        ],
    )
    def test_no_answer(self, op, fact, rule, reason):
        outcome = compare_operator(op, fact, rule, **_PLAIN)
        assert isinstance(outcome, Uncomparable) and not outcome
        assert outcome.issue.reason == reason
        assert outcome.issue.operator == op and outcome.issue.field == "v"
        assert evaluate_operator(op, fact, rule, **_PLAIN) is False

    @pytest.mark.parametrize(
        ("op", "fact", "rule", "answer"),
        [
            ("==", None, 5, False),
            ("!=", "abc", 5, True),
            ("==", math.nan, math.nan, False),
            ("!=", math.nan, 5, True),
            (">", 7, 5, True),
            (">", 3, 5, False),
            ("in", "abc", [5], False),
            ("starts_with", 5, "5", True),
        ],
    )
    def test_answers_that_exist(self, op, fact, rule, answer):
        assert compare_operator(op, fact, rule, **_PLAIN) is answer

    def test_strict_types_order_numbers_only(self):
        strict = {**_PLAIN, "strict_type_comparison": True}
        outcome = compare_operator(">", True, 0, **strict)
        assert isinstance(outcome, Uncomparable)
        assert outcome.issue.reason == "strict_type_comparison orders two numbers only"

    @pytest.mark.parametrize(("op", "answer"), [("==", False), ("!=", True)])
    def test_strict_types_never_equal_across_types(self, op, answer):
        strict = {**_PLAIN, "strict_type_comparison": True}
        assert compare_operator(op, 5, "5", **strict) is answer
        assert compare_operator(op, True, 1, **strict) is answer

    def test_the_setting_is_validated(self):
        with pytest.raises(ValueError, match="uncomparable must be"):
            EngineConfig(uncomparable="maybe")


NOT_GT = _rule(1, ~(F("v") > 5))
GT = _rule(2, F("v") > 5)
DECIDED_FALSE = _rule(3, (F("v") > 5) & (F("always") == 0))
DECIDED_TRUE = _rule(4, (F("v") > 5) | (F("always") == 1))
UNDECIDED_AND = _rule(5, (F("v") > 5) & (F("always") == 1))
FACT = {"v": "abc", "always": 1}
ISSUE = ("v", ">", "str", "int")


class TestDefaultMode:
    def test_no_match_and_not_fires_as_before(self):
        result = _engine(NOT_GT, GT).evaluate(FACT)
        assert result.fired_rules == [1]

    def test_lists_the_issue(self):
        result = _engine(GT).evaluate(FACT)
        assert _keys(result) == {ISSUE}
        issue = result.comparison_issues[0]
        assert issue.reason == "these types cannot be ordered"
        assert issue.to_dict()["fact_type"] == "str"

    def test_warns_once_per_issue_at_the_callers_line(self):
        engine = _engine(GT)
        with pytest.warns(ComparisonWarning, match="Cannot compare field 'v' with '>'") as caught:
            engine.evaluate(FACT)
        assert caught[0].filename == __file__
        with warnings.catch_warnings():
            warnings.simplefilter("error", ComparisonWarning)
            engine.evaluate(FACT)  # already warned about

    def test_lists_an_issue_once_however_many_rules_read_it(self):
        rules = [_rule(i, F("v") > i) for i in range(1, 6)]
        assert len(_engine(*rules).evaluate(FACT).comparison_issues) == 1

    @pytest.mark.parametrize("rule", [DECIDED_FALSE, DECIDED_TRUE], ids=["AND false", "OR true"])
    def test_an_issue_that_decides_nothing_is_not_reported(self, rule):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ComparisonWarning)
            result = _engine(rule).evaluate(FACT)
        assert result.comparison_issues == []

    def test_a_fact_with_answers_only_reports_nothing(self):
        assert _engine(NOT_GT, GT).evaluate({"v": 7}).comparison_issues == []


class TestFalseMode:
    def test_silent_but_still_listed(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ComparisonWarning)
            result = _engine(NOT_GT, GT, uncomparable="false").evaluate(FACT)
        assert result.fired_rules == [1]
        assert _keys(result) == {ISSUE}


class TestUnknownMode:
    @pytest.mark.parametrize(
        "options", [{}, {"alpha_prefilter": False}, {"compile_conditions": True}]
    )
    def test_not_over_it_does_not_fire(self, options):
        engine = PhreakEngine(config=EngineConfig(uncomparable="unknown"), **options)
        engine.load_rules([NOT_GT, DECIDED_TRUE, UNDECIDED_AND])
        result = engine.evaluate(FACT)
        assert result.fired_rules == [4], "only the rule an OR decided fires"
        assert _keys(result) == {ISSUE}

    def test_a_definite_not_still_fires(self):
        engine = _engine(NOT_GT, uncomparable="unknown")
        assert engine.evaluate({"v": 3}).fired_rules == [1]

    def test_with_missing_field_unknown_too(self):
        rule = _rule(1, ~((F("missing") == 1) & (F("v") > 5)))
        fact = {"v": "abc"}
        assert _engine(rule).evaluate(fact).fired_rules == [1]
        both = _engine(rule, uncomparable="unknown", missing_field="unknown")
        assert both.evaluate(fact).fired_rules == []

    def test_does_not_warn(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", ComparisonWarning)
            _engine(NOT_GT, uncomparable="unknown").evaluate(FACT)


class TestRaiseMode:
    def test_raises_naming_field_operator_and_types(self):
        with pytest.raises(UncomparableValuesError) as caught:
            _engine(GT, uncomparable="raise").evaluate(FACT)
        assert caught.value.issue == ComparisonIssue(
            "v", ">", "str", "int", "these types cannot be ordered"
        )
        assert "fact value is str, rule value is int" in str(caught.value)
        assert caught.value.code == "UNCOMPARABLE_VALUES"

    def test_a_decided_rule_does_not_raise(self):
        engine = _engine(DECIDED_FALSE, DECIDED_TRUE, uncomparable="raise")
        assert engine.evaluate(FACT).fired_rules == [4]

    def test_the_error_survives_pickling(self):
        error = UncomparableValuesError(ComparisonIssue("v", ">", "str", "int", "why"))
        restored = pickle.loads(pickle.dumps(error))
        assert restored.issue == error.issue and str(restored) == str(error)


class TestEveryWayOfEvaluating:
    def test_evaluate_follows_the_process_config(self, process_config):
        assert _keys(evaluate(GT, FACT)) == {ISSUE}
        process_config(EngineConfig(uncomparable="unknown"))
        assert evaluate(NOT_GT, FACT).fired_rules == []
        process_config(EngineConfig(uncomparable="raise"))
        with pytest.raises(UncomparableValuesError):
            evaluate(GT, FACT)

    def test_streaming_does_not_cache_a_result_it_must_report(self):
        # Streaming caches a rule's result by the values it reads. Values seen
        # before would reuse it and skip the report, so such results are not
        # cached.
        engine = PhreakEngine(streaming_mode=True)
        engine.load_rules([_rule(1, (F("v") > 5) & (F("w") == 1))])
        assert _keys(engine.evaluate({"v": "abc", "w": 1})) == {ISSUE}
        assert _keys(engine.evaluate({"v": "abc", "w": 2})) == set(), "decided by w"
        assert _keys(engine.evaluate({"v": "abc", "w": 1})) == {ISSUE}

    def test_the_thread_pool_lists_issues(self):
        engine = PhreakEngine(config=EngineConfig(parallel_threshold=0))
        engine.load_rules([GT, NOT_GT])
        result = engine.evaluate(FACT)
        assert result.fired_rules == [1]
        assert _keys(result) == {ISSUE}

    def test_worker_processes_list_issues_and_the_parent_warns_once(self):
        engine = _engine(GT)
        with pytest.warns(ComparisonWarning) as caught:
            results = engine.evaluate_batch([FACT, FACT, {"v": 7}], workers=2)
        assert [_keys(r) for r in results] == [{ISSUE}, {ISSUE}, set()]
        assert len([w for w in caught if w.category is ComparisonWarning]) == 1

    def test_worker_processes_raise_in_the_parent(self):
        engine = _engine(GT, uncomparable="raise")
        with pytest.raises(UncomparableValuesError):
            engine.evaluate_batch([{"v": 7}, FACT], workers=2)

    def test_cross_fact_engine_warns_and_raises(self, process_config):
        from fluxrules.engine.cross_fact import CrossFactEngine, CrossFactRule, Pattern

        rule = CrossFactRule(
            id=1,
            name="c",
            patterns=[Pattern(var="f", fact_type="Fact", constraints=[("v", ">", 5)])],
            action="hit",
        )
        engine = CrossFactEngine()
        engine.load_rules([rule])
        with pytest.warns(ComparisonWarning):
            engine.insert("Fact", FACT)
        process_config(EngineConfig(uncomparable="raise"))
        engine = CrossFactEngine()
        engine.load_rules([rule])
        with pytest.raises(UncomparableValuesError):
            engine.insert("Fact", FACT)

    def test_prefiltered_evaluator_lists_issues_of_facts_that_fired(self):
        pytest.importorskip("sqlalchemy")
        from sqlalchemy import create_engine

        from fluxrules.prefilter import PreFilteredEvaluator
        from fluxrules.prefilter.sql_store import FactPreFilterStore

        store = FactPreFilterStore(engine=create_engine("sqlite://"))
        try:
            results, _ = PreFilteredEvaluator(_engine(NOT_GT), store).run([FACT])
        finally:
            store.dispose()
        assert [_keys(r) for r in results] == [{ISSUE}]


class TestPrefilteredEvaluatorKeepsBooleanThresholds:
    """``v > True`` under strict types cannot be ordered for any fact.

    The SQL store must not screen ``{"v": 0}`` out as ``0 > 1``, or the
    issue would go unreported and ``"raise"`` would not raise.
    """

    @pytest.mark.parametrize("mode", [None, "raise"])
    def test_a_number_fact_reaches_the_engine(self, mode):
        from sqlalchemy import create_engine

        from fluxrules.prefilter import PreFilteredEvaluator
        from fluxrules.prefilter.sql_store import FactPreFilterStore

        config = EngineConfig(strict_type_comparison=True, uncomparable=mode)
        engine = PhreakEngine(config=config)
        engine.load_rules([_rule(1, F("v") > True)])
        store = FactPreFilterStore(engine=create_engine("sqlite://"))
        try:
            if mode == "raise":
                with pytest.raises(UncomparableValuesError):
                    PreFilteredEvaluator(engine, store).run([{"v": 0}])
            else:
                with pytest.warns(ComparisonWarning):
                    _, stats = PreFilteredEvaluator(engine, store).run([{"v": 0}])
                assert stats.candidate_facts == 1
        finally:
            store.dispose()


class TestPrefilterKeepsWhatTheEngineMustReport:
    @pytest.mark.parametrize("value", [None, math.nan, Decimal("NaN")])
    def test_none_and_nan_reach_the_engine(self, value):
        result = _engine(GT).evaluate({"v": value})
        assert result.fired_rules == []
        assert len(result.comparison_issues) == 1

    def test_a_decimal_nan_does_not_crash_the_default_engine(self):
        # Used to raise decimal.InvalidOperation from the alpha prefilter.
        assert _engine(GT, NOT_GT).evaluate({"v": Decimal("NaN")}).fired_rules == [1]

    @pytest.mark.parametrize("op", [">", ">=", "<", "<="])
    @pytest.mark.parametrize("value", [5, 5.5, Decimal("5"), "m", date(2024, 1, 1)])
    def test_fast_tests_keep_what_the_full_tests_keep(self, op, value):
        # A fact with no None or NaN uses ordering tests without the NaN test.
        from fluxrules.prefilter.predicate_index import (
            _MISSING,
            _make_test,
            _orderable,
            _test_or_keep,
        )

        full = _make_test(op, value)
        fast = _make_test(op, value, orderable=True)
        for v in [0, 5, 10, 4.9, 5.5, True, Decimal("7"), "a", "z", date(2025, 1, 1), [1]]:
            assert _orderable({"v": v, "w": 1})
            assert _test_or_keep(fast, v) == _test_or_keep(full, v), v
        assert fast(_MISSING) is full(_MISSING) is False

    @pytest.mark.parametrize("value", [None, math.nan, Decimal("NaN")])
    def test_none_or_nan_in_another_field_uses_the_full_tests(self, value):
        from fluxrules.prefilter.predicate_index import _orderable

        assert not _orderable({"v": 1, "w": value})

    def test_strict_types_keep_a_boolean_for_the_engine(self):
        engine = _engine(_rule(1, F("v") > 0), strict_type_comparison=True)
        result = engine.evaluate({"v": False})
        assert _keys(result) == {("v", ">", "bool", "int")}


class TestRelevanceWalk:
    """``evaluate_with_issues`` on every node type it knows."""

    @staticmethod
    def _walk(node, facts):
        from fluxrules.domain.conditions.uncomparable_rules import evaluate_with_issues

        def leaf(n, f):
            return compare_operator(
                n["op"],
                f[n["field"]],
                n["value"],
                field_present=True,
                strict_null_handling=False,
                strict_type_comparison=False,
                boolean_string_coercion=False,
                field=n["field"],
            )

        value, issues = evaluate_with_issues(
            node,
            facts,
            leaf=leaf,
            other=lambda n, f: True,
            empty=True,
            missing_unknown=False,
        )
        return value, [i.reason for i in issues]

    BAD = {"type": "condition", "field": "v", "op": ">", "value": 5}

    @pytest.mark.parametrize(
        ("node", "expected"),
        [
            ("not a node", (False, [])),
            ({"type": "and", "conditions": [BAD]}, (None, ["these types cannot be ordered"])),
            ({"type": "or", "conditions": [BAD, {"type": "custom"}]}, (True, [])),
            ({"type": "group", "op": "AND", "children": []}, (True, [])),
            ({"type": "not"}, (True, [])),
            ({"type": "exists", "field": "v"}, (True, [])),
            ({"type": "exists", "field": "w"}, (False, [])),
            ({"type": "exists", "condition": BAD}, (None, ["these types cannot be ordered"])),
            ({"type": "exists"}, (False, [])),
            ({"type": "accumulate"}, (True, [])),
        ],
    )
    def test_node_types(self, node, expected):
        assert self._walk(node, {"v": "abc"}) == expected


class TestReasons:
    def test_a_comparison_that_raises_names_its_reason(self):
        from decimal import InvalidOperation

        from fluxrules.engine.operators import REASON_MEMBERSHIP, REASON_NAN, _failure_reason

        assert _failure_reason(">", Decimal("NaN"), 1, InvalidOperation()) == REASON_NAN
        assert _failure_reason(">", 1, 2, ValueError()) == "the comparison raised ValueError"
        assert _failure_reason("in", 1, 2, TypeError()) == REASON_MEMBERSHIP
        assert _failure_reason("starts_with", 1, 2, ValueError()) == (
            "the comparison raised ValueError"
        )

    def test_compare_refuses_an_unknown_operator(self):
        from fluxrules.domain.errors import UnknownOperatorError
        from fluxrules.domain.predicates import compare

        with pytest.raises(UnknownOperatorError):
            compare("???", 1, 2)

    def test_current_mode_reads_the_scope_or_the_config(self, process_config):
        from fluxrules.engine.uncomparable import comparison_scope, current_mode

        set_config(EngineConfig(uncomparable="unknown"))
        assert current_mode() == "unknown"
        with comparison_scope("raise"):
            assert current_mode() == "raise"


class TestFlatRules:
    """The reference evaluator's flat conjunction, for rules with no tree."""

    @staticmethod
    def _rule(*conditions):
        from types import SimpleNamespace

        from fluxrules.domain.models import RuleCondition

        nodes = tuple(RuleCondition(fact=f, operator=o, value=v) for f, o, v in conditions)
        return SimpleNamespace(id=1, conditions=None, condition_nodes=nodes)

    def _evaluate(self, rule, facts, mode=None):
        from fluxrules.engine.uncomparable import comparison_scope
        from fluxrules.services.reference_evaluator import ReferenceEvaluator

        with comparison_scope(mode) as scope:
            fired = ReferenceEvaluator()._evaluate_rule(rule, facts)
        return fired, [i.reason for i in scope.issues]

    def test_reports_an_unmade_comparison_when_nothing_else_decides(self):
        rule = self._rule(("v", ">", 5), ("w", "==", 1))
        assert self._evaluate(rule, {"v": "abc", "w": 1}, "false") == (
            False,
            ["these types cannot be ordered"],
        )

    def test_a_definite_false_decides_without_a_report(self):
        rule = self._rule(("v", ">", 5), ("w", "==", 1))
        assert self._evaluate(rule, {"v": "abc", "w": 2}, "false") == (False, [])

    def test_true_and_missing(self):
        rule = self._rule(("v", ">", 5))
        assert self._evaluate(rule, {"v": 6}) == (True, [])
        assert self._evaluate(rule, {"x": 6}) == (False, [])

    def test_a_typo_raises(self):
        from fluxrules.domain.errors import FieldNotFoundError

        with pytest.raises(FieldNotFoundError):
            self._evaluate(self._rule(("Amount", ">", 5)), {"amount": 6})


class TestWorkerChunk:
    def test_a_worker_lists_issues_without_warning(self):
        from fluxrules.engine.runtime import worker_pool

        worker_pool._init_worker(PhreakEngine, {}, [_rule(1, ~(F("v") > 5))])
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", ComparisonWarning)
                results, _, error, issues = worker_pool._eval_chunk((0, [{"v": "abc"}], True, True))
        finally:
            worker_pool._WORKER_ENGINE = None
        assert error is None and results == [[1]]
        assert [(i, issue.reason) for i, issue in issues] == [(0, "these types cannot be ordered")]


class TestCompiledLeafWithoutMemo:
    def test_an_unhashable_fact_value_reports(self):
        # The memo cannot key a bytearray, so the leaf compares directly.
        engine = PhreakEngine(compile_conditions=True)
        engine.load_rules([_rule(1, ~(F("v") > 5))])
        result = engine.evaluate({"v": bytearray(b"a")})
        assert result.fired_rules == [1]
        assert _keys(result) == {("v", ">", "bytearray", "int")}


pytest.importorskip("typer")

from typer.testing import CliRunner  # noqa: E402

from fluxrules.cli.main import app  # noqa: E402

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FLUXRULES_CONFIG_FILE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    rules = [
        {"id": 1, "name": "big", "action": "hit", "conditions": GT.conditions},
        {"id": 2, "name": "not_big", "action": "hit", "conditions": NOT_GT.conditions},
    ]
    (tmp_path / "rules.json").write_text(json.dumps(rules))
    (tmp_path / "fact.json").write_text(json.dumps(FACT))
    return tmp_path


class TestCli:
    def test_json_lists_the_issues(self, project):
        result = runner.invoke(app, ["evaluate", "rules.json", "fact.json", "--format", "json"])
        assert result.exit_code == 0, result.output
        body = json.loads(result.stdout)
        assert [r["id"] for r in body["matched_rules"]] == [2]
        assert body["comparison_issues"] == [
            {
                "field": "v",
                "operator": ">",
                "fact_type": "str",
                "rule_type": "int",
                "reason": "these types cannot be ordered",
            }
        ]

    def test_text_output_lists_the_issues(self, project):
        result = runner.invoke(app, ["evaluate", "rules.json", "fact.json"])
        assert result.exit_code == 0, result.output
        text = " ".join(result.stdout.split())
        assert "Comparisons that could not be made" in text
        assert "Cannot compare field 'v' with '>'" in text

    def test_unknown_from_the_config_file(self, project):
        (project / "fluxrules.yaml").write_text("uncomparable: unknown\n")
        result = runner.invoke(app, ["evaluate", "rules.json", "fact.json", "--format", "json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["matched_rules"] == []

    def test_raise_from_the_config_file_exits_1(self, project):
        (project / "fluxrules.yaml").write_text("uncomparable: raise\n")
        result = runner.invoke(app, ["evaluate", "rules.json", "fact.json"])
        assert result.exit_code == 1
        assert "Cannot compare field 'v'" in " ".join(result.output.split())

    def test_a_bad_value_in_a_found_config_is_ignored(self, project):
        (project / "fluxrules.yaml").write_text("uncomparable: maybe\n")
        result = runner.invoke(app, ["evaluate", "rules.json", "fact.json", "--format", "json"])
        assert result.exit_code == 0, result.output
        assert "Ignoring" in result.stderr

    def test_a_bad_value_in_an_explicit_config_fails(self, project):
        (project / "settings.yaml").write_text("uncomparable: maybe\n")
        result = runner.invoke(
            app, ["evaluate", "rules.json", "fact.json", "--config", "settings.yaml"]
        )
        assert result.exit_code != 0
        assert "uncomparable must be 'false', 'unknown', 'raise' or null" in " ".join(
            result.output.split()
        )


pytest.importorskip("fastapi")


class TestHttpApi:
    def test_raise_returns_422_with_the_issue(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from fluxrules.api.handlers import register_exception_handlers

        api = FastAPI()
        register_exception_handlers(api)

        @api.get("/boom")
        def boom():
            raise UncomparableValuesError(
                ComparisonIssue("v", ">", "str", "int", "these types cannot be ordered")
            )

        response = TestClient(api).get("/boom")
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "UNCOMPARABLE_VALUES"
        assert body["comparison_issue"]["field"] == "v"
