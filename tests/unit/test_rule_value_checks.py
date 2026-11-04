"""Rule values are checked when rules load.

- A value that does not suit its operator (``F("amount") > None``) warns with
  ``RuleValueWarning`` when the rule is created; the rule still loads.
- With ``fact_schema=``, a value that does not fit its field's type raises
  ``RuleValueError``; an ISO date string on a date field becomes a date.
- YAML files are read as written (YAML 1.2): ``NO`` is the text ``"NO"``, and
  each value FluxRules 1.1 read differently warns with ``YamlValueWarning``.
- ``fluxrules.validate()`` and ``fluxrules validate`` list all of these.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import math
import pickle
import warnings
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Union

import pytest
from pydantic import BaseModel

from fluxrules import (
    F,
    Rule,
    RuleValueError,
    RuleValueWarning,
    YamlValueWarning,
    validate,
)
from fluxrules.adapters.loaders.yaml_reading import load_yaml
from fluxrules.domain.conditions.rule_values import reset_value_warnings, value_problems
from fluxrules.domain.conditions.schema_values import field_kind
from fluxrules.engine.configuration import EngineConfig
from fluxrules.engine.phreak import PhreakEngine


@pytest.fixture(autouse=True)
def fresh_warnings():
    """Each test sees each warning once, whatever ran before it."""
    reset_value_warnings()
    yield
    reset_value_warnings()


def _leaf(op: str, value: Any, field: str = "v") -> dict[str, Any]:
    return {"type": "condition", "field": field, "op": op, "value": value}


def _rule(conditions: Any, rid: int = 1, name: str = "r") -> Rule:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuleValueWarning)
        return Rule(id=rid, name=name, conditions=conditions, action="a")


# --- value against operator ---------------------------------------------------


class TestValueAgainstOperator:
    @pytest.mark.parametrize(
        ("op", "value", "expected"),
        [
            (">", None, "needs a number, text, a date or a time, but got None"),
            (">=", True, "but got the boolean True"),
            ("<", [1, 2], "but got [1, 2] (a list)"),
            ("<=", {"a": 1}, "(a mapping)"),
            ("gt", None, "'>' needs a number"),
            (">", math.nan, "cannot order anything against NaN"),
            (">", Decimal("NaN"), "cannot order anything against NaN"),
            ("regex", "(", "the pattern '(' does not compile"),
        ],
    )
    def test_warns_when_the_rule_is_created(self, op, value, expected):
        with pytest.warns(RuleValueWarning, match="can never match") as caught:
            rule = Rule(id=1, name="r", conditions=_leaf(op, value), action="a")
        assert expected in str(caught[0].message)
        assert rule.conditions["value"] == value or value != value  # NaN is kept too

    @pytest.mark.parametrize(
        ("op", "value", "expected"),
        [
            (
                "starts_with",
                75,
                '\'starts_with\' compares text, so the number 75 is read as the text "75". Write "75" to say so.',
            ),
            ("ends_with", None, 'so None is read as the text "None"'),
            ("regex", 5, "'regex' compares text, so the number 5 is read as the text \"5\""),
        ],
    )
    def test_a_value_read_as_text_warns_without_never_match(self, op, value, expected):
        # starts_with, ends_with and regex compare str() of both sides, so the
        # rule can match; the warning says how the value is read.
        with pytest.warns(RuleValueWarning) as caught:
            Rule(id=1, name="r", conditions=_leaf(op, value), action="a")
        message = str(caught[0].message)
        assert expected in message and "never match" not in message

    def test_a_number_read_as_text_still_matches(self):
        rule = _rule(F("zip").starts_with(75))
        engine = PhreakEngine()
        engine.load_rules([rule])
        assert engine.evaluate({"zip": "75001"}).fired_rules == [1]
        assert engine.evaluate({"zip": 75001}).fired_rules == [1]

    @pytest.mark.parametrize(
        ("op", "value"),
        [
            (">", 5),
            (">", 5.5),
            (">", Decimal("5")),
            (">", "m"),
            (">", dt.date(2024, 1, 1)),
            (">", dt.datetime(2024, 1, 1, 9)),
            (">", dt.time(9, 30)),
            (">", dt.timedelta(days=1)),
            ("starts_with", "75"),
            ("regex", r"^\d+$"),
            ("==", None),
            ("==", True),
            ("in", [None, True]),
            ("contains", 5),
        ],
    )
    def test_suitable_values_do_not_warn(self, op, value):
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuleValueWarning)
            Rule(id=1, name="r", conditions=_leaf(op, value), action="a")

    def test_the_rule_still_loads_and_evaluates_as_before(self):
        rule = _rule(~(F("v") > None))
        engine = PhreakEngine()
        engine.load_rules([rule])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert engine.evaluate({"v": 1}).fired_rules == [1]

    def test_warns_once_per_problem(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for _ in range(3):
                Rule(id=1, name="r", conditions=F("v") > None, action="a")
        assert [w.category for w in caught] == [RuleValueWarning]

    def test_names_the_condition_in_a_group(self):
        problems = value_problems(((F("a") == 1) & (F("v") > None)).to_dict())
        assert problems == [
            "Condition at 'root.children[1]' on field 'v': '>' needs a number, text, "
            "a date or a time, but got None. The condition can never match."
        ]

    def test_validate_lists_the_problems_without_blocking_evaluate(self):
        from fluxrules import evaluate

        rule = _rule(~(F("v") > None))
        problems = [i for i in validate([rule]) if "can never match" in i]
        assert len(problems) == 1 and problems[0].startswith("Rule '1': Condition")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            assert evaluate(rule, {"v": 1}).fired_rules == [1]


# --- value against the fact schema ----------------------------------------------


class Order(BaseModel):
    amount: float
    count: int = 0
    price: Decimal = Decimal(0)
    country: str = ""
    vip: bool = False
    placed: dt.date = dt.date(2024, 1, 1)
    at: dt.datetime | None = None
    tag: Annotated[str, "label"] = ""
    either: int | str = 0
    anything: Any = None
    status: Literal["open", "closed"] = "open"
    items: list[int] = []


def _engine(*conditions: Any, **kwargs: Any) -> PhreakEngine:
    engine = PhreakEngine(fact_schema=Order, **kwargs)
    engine.load_rules([_rule(c, rid=i + 1, name=f"r{i + 1}") for i, c in enumerate(conditions)])
    return engine


class TestFieldKind:
    @pytest.mark.parametrize(
        ("annotation", "kind"),
        [
            (float, ("number", "float")),
            (int, ("number", "int")),
            (Decimal, ("number", "Decimal")),
            (str, ("text", "str")),
            (bool, ("bool", "bool")),
            (dt.date, ("date", "date")),
            (dt.datetime, ("datetime", "datetime")),
            (Optional[float], ("number", "float")),  # noqa: UP045
            (float | None, ("number", "float")),
            (Annotated[int, "x"], ("number", "int")),
            (Union[int, str], None),  # noqa: UP007
            (Any, None),
            (Literal["a"], None),
            (list[int], None),
        ],
    )
    def test_kinds(self, annotation, kind):
        assert field_kind(annotation) == kind


class TestValueAgainstSchema:
    @pytest.mark.parametrize(
        ("condition", "message"),
        [
            (
                F("amount") > "100.1",
                "field 'amount' is float in Order, but the rule compares it with the text "
                "'100.1'. Write 100.1 without quotes to compare numbers.",
            ),
            (F("amount") == "abc", "compares it with the text 'abc'. Write a number."),
            (F("count") == True, "compares it with the boolean True. Write a number."),  # noqa: E712
            (
                F("country") == 5,
                "field 'country' is str in Order, but the rule compares it with the number 5. Write \"5\" in quotes to compare text.",
            ),
            (F("tag") == 5, "field 'tag' is str in Order"),
            (F("vip") == "yes", "compares it with the text 'yes'. Write true or false."),
            (F("vip") == "true", "Write true without quotes."),
            (F("placed") >= "May 1", "Write an ISO date such as 2024-05-01."),
            (F("placed") >= "2024-05-01T10:00:00", "Write the date only, such as 2024-05-01."),
            (F("placed") >= dt.datetime(2024, 5, 1), "A date and a datetime cannot be compared"),
            (F("at") > "2024-05-01", "Write a date and time, such as 2024-05-01T00:00:00."),
            (F("at") > dt.date(2024, 5, 1), "A date and a datetime cannot be compared"),
            (F("amount").isin([1, "2"]), "compares it with the text '2'"),
            (F("count").contains("1"), "'contains' needs text or a collection"),
            (F("country").contains(5), "the rule looks for the number 5 in it"),
        ],
    )
    def test_refuses_to_load(self, condition, message):
        engine = PhreakEngine(fact_schema=Order)
        with pytest.raises(RuleValueError) as raised:
            engine.load_rules([_rule(condition, name="big")])
        assert message in str(raised.value)
        assert str(raised.value).startswith("Rule 'big': ")
        assert engine.rule_repository.rules == {}

    @pytest.mark.parametrize(
        "condition",
        [
            F("amount") > 100,
            F("amount") > 100.5,
            F("amount") > Decimal("100.5"),
            F("price") <= 3,
            F("amount") == None,  # noqa: E711
            F("country") == "NO",
            F("vip") == True,  # noqa: E712
            F("placed") >= dt.date(2024, 5, 1),
            F("at") > dt.datetime(2024, 5, 1, 9),
            F("amount").isin([1, 2.5, None]),
            F("country").starts_with("N"),
            F("amount").starts_with("1"),
            F("count").regex("^7"),
            F("country").contains("O"),
            F("either") == "x",
            F("anything") == "x",
            F("status") == "nope",
            F("items").contains(5),
        ],
    )
    def test_loads_values_that_fit(self, condition):
        _engine(condition)

    def test_iso_dates_become_dates(self):
        engine = _engine(F("placed") >= "2024-05-01", F("at") > "2024-05-01T09:30:00")
        stored = {r.id: r.conditions["value"] for r in engine.rule_repository.rules.values()}
        assert stored == {1: dt.date(2024, 5, 1), 2: dt.datetime(2024, 5, 1, 9, 30)}
        fact = {"amount": 1.0, "placed": dt.date(2024, 6, 1), "at": dt.datetime(2024, 6, 1)}
        assert sorted(engine.evaluate(fact).fired_rules) == [1, 2]

    def test_iso_dates_in_a_list_become_dates(self):
        engine = _engine(F("placed").isin(["2024-05-01", "2024-05-02"]))
        (rule,) = engine.rule_repository.rules.values()
        assert rule.conditions["value"] == [dt.date(2024, 5, 1), dt.date(2024, 5, 2)]

    def test_the_callers_rule_is_not_changed(self):
        rule = _rule(F("placed") >= "2024-05-01")
        PhreakEngine(fact_schema=Order).load_rules([rule])
        assert rule.conditions["value"] == "2024-05-01"

    def test_boolean_string_coercion_accepts_true_and_false_text(self):
        config = EngineConfig(boolean_string_coercion=True)
        _engine(F("vip") == "true", config=config)

    def test_the_error_carries_its_details_and_pickles(self):
        with pytest.raises(RuleValueError) as raised:
            _engine(F("amount") > "100.1")
        error = raised.value
        assert (error.field, error.rule, error.schema_name, error.value) == (
            "amount",
            "r1",
            "Order",
            "100.1",
        )
        assert isinstance(error, ValueError) and error.code == "RULE_VALUE_TYPE"
        copy = pickle.loads(pickle.dumps(error))
        assert (copy.summary, copy.field, copy.value) == (error.summary, "amount", "100.1")

    def test_validate_lists_every_problem(self):
        rules = [
            _rule(F("amount") > "1", rid=1, name="a"),
            _rule((F("country") == 5) & (F("vip") == "no"), rid=2, name="b"),
            _rule(F("amout") > 1, rid=3, name="c"),
        ]
        issues = validate(rules, fact_schema=Order)
        assert len(issues) == 4
        assert issues[0].startswith("Rule 'c' references unknown field 'amout'")
        assert [i.split(": ")[0] for i in issues[1:]] == ["Rule 'a'", "Rule 'b'", "Rule 'b'"]
        assert "field 'amount' is float in Order" in issues[1]

    def test_validate_without_a_schema_skips_the_schema_checks(self):
        assert validate([_rule(F("amount") > "1")]) == []

    def test_the_yaml_loader_converts_and_refuses(self, tmp_path: Path):
        from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml

        path = tmp_path / "rules.yaml"
        path.write_text(
            "- id: 1\n  name: r\n  action: a\n"
            "  conditions: {type: condition, field: placed, op: '>=', value: '2024-05-01'}\n"
        )
        (rule,) = load_rules_from_yaml(str(path), fact_schema=Order)
        assert rule["conditions"]["value"] == dt.date(2024, 5, 1)
        path.write_text(
            "- id: 1\n  name: r\n  action: a\n"
            "  conditions: {type: condition, field: amount, op: '>', value: '100.1'}\n"
        )
        with pytest.raises(RuleValueError, match="Write 100.1 without quotes"):
            load_rules_from_yaml(str(path), fact_schema=Order)


# --- YAML read as written --------------------------------------------------------


def _read(text: str) -> tuple[Any, list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = load_yaml(io.StringIO(text), source="rules.yaml")
    return data, [str(w.message) for w in caught if w.category is YamlValueWarning]


class TestYamlReadAsWritten:
    @pytest.mark.parametrize(
        ("text", "value", "warning"),
        [
            (
                "NO",
                "NO",
                'NO is read as the text "NO"; FluxRules 1.1 read it as the boolean false. Write false if you mean the boolean false.',
            ),
            ("yes", "yes", "FluxRules 1.1 read it as the boolean true"),
            ("on", "on", "the boolean true"),
            ("Off", "Off", "the boolean false"),
            (
                "0755",
                "0755",
                'read as the text "0755"; FluxRules 1.1 read it as the number 493. Write 493',
            ),
            ("1:30", "1:30", "FluxRules 1.1 read it as the number 90"),
            ("1_000", "1_000", "the number 1000"),
            (
                "1e3",
                1000.0,
                '1e3 is read as the number 1000.0; FluxRules 1.1 read it as the text "1e3". Write "1e3" in quotes if you mean the text.',
            ),
            ("1.0e3", 1000.0, 'the text "1.0e3"'),
            ("0o755", 493, 'the text "0o755"'),
        ],
    )
    def test_traps_read_as_written_and_warn(self, text, value, warning):
        data, messages = _read(f"rule: x\nvalue: {text}\n")
        assert data["value"] == value
        assert messages == [m for m in messages if m.startswith("rules.yaml, line 2: ")]
        assert len(messages) == 1 and warning in messages[0]

    @pytest.mark.parametrize(
        ("text", "value"),
        [
            ("true", True),
            ("False", False),
            ("TRUE", True),
            ("5", 5),
            ("-3", -3),
            ("+5", 5),
            ("0", 0),
            ("5.5", 5.5),
            (".5", 0.5),
            ("-2.5e-3", -0.0025),
            ("0x1F", 31),
            ("null", None),
            ("~", None),
            ("", None),
            ("2024-05-01", dt.date(2024, 5, 1)),
            ('"NO"', "NO"),
            ("'0755'", "0755"),
            ("abc", "abc"),
        ],
    )
    def test_ordinary_values_read_as_before_and_do_not_warn(self, text, value):
        data, messages = _read(f"value: {text}\n")
        assert data["value"] == value and type(data["value"]) is type(value)
        assert messages == []

    def test_infinity_and_nan(self):
        data, messages = _read("a: .inf\nb: -.Inf\nc: .nan\n")
        assert data["a"] == math.inf and data["b"] == -math.inf and math.isnan(data["c"])
        assert messages == []

    def test_warnings_come_in_line_order(self):
        _, messages = _read("a: [on, off]\nb: NO\n")
        assert [m.split(": ")[0] for m in messages] == [
            "rules.yaml, line 1",
            "rules.yaml, line 1",
            "rules.yaml, line 2",
        ]
        assert [m.split(": ")[1].split()[0] for m in messages] == ["on", "off", "NO"]

    def test_a_rule_file_compares_with_the_text(self, tmp_path: Path):
        from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml

        path = tmp_path / "rules.yaml"
        path.write_text(
            "- id: 1\n  name: norway\n  action: a\n"
            "  conditions: {type: condition, field: country, op: '==', value: NO}\n"
        )
        with pytest.warns(YamlValueWarning, match=r"rules.yaml, line 4: NO is read as the text"):
            rules = load_rules_from_yaml(str(path))
        engine = PhreakEngine()
        engine.load_rules(rules)
        assert engine.evaluate({"country": "NO"}).fired_rules == [1]

    def test_deployment_config_refuses_text_for_on_off_settings(self, tmp_path: Path):
        from fluxrules.config.deployment import ConfigValidationError, DeploymentConfig

        path = tmp_path / "fluxrules.yaml"
        path.write_text("requirements:\n  sortable_ids: yes\n")
        with (
            pytest.warns(YamlValueWarning),
            pytest.raises(ConfigValidationError, match="sortable_ids must be true or false"),
        ):
            DeploymentConfig.from_file(path)
        path.write_text("storage_sensitive: true\n")
        assert DeploymentConfig.from_file(path).storage_sensitive is True


# --- CLI ------------------------------------------------------------------------

pytest.importorskip("typer")

from typer.testing import CliRunner  # noqa: E402

from fluxrules.cli.main import app  # noqa: E402

runner = CliRunner()

MODELS = """
import datetime as dt
from pydantic import BaseModel


class Order(BaseModel):
    amount: float
    placed: dt.date
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FLUXRULES_CONFIG_FILE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "models.py").write_text(MODELS)
    return tmp_path


def _yaml_rule(field: str, op: str, value: str) -> str:
    return (
        f"- id: 1\n  name: r\n  action: a\n"
        f"  conditions: {{type: condition, field: {field}, op: '{op}', value: {value}}}\n"
    )


class TestCli:
    def test_validate_lists_operator_schema_and_yaml_problems(self, project: Path):
        (project / "rules.yaml").write_text(
            "- id: 1\n  name: r\n  action: a\n"
            "  conditions:\n    type: group\n    op: AND\n    children:\n"
            "      - {type: condition, field: amount, op: '>', value: '100.1'}\n"
            "      - {type: condition, field: amount, op: '<', value: null}\n"
            "      - {type: condition, field: placed, op: '==', value: yes}\n"
        )
        result = runner.invoke(app, ["validate", "rules.yaml", "--schema", "models.py:Order"])
        assert result.exit_code == 1, result.output
        issues = json.loads(result.output)["issues"]
        assert any("line 10: yes is read as the text" in i for i in issues)
        assert any("'<' needs a number" in i for i in issues)
        assert any("Write 100.1 without quotes" in i for i in issues)
        assert any("field 'placed' is date in Order" in i for i in issues)

    def test_validate_passes_clean_rules(self, project: Path):
        (project / "rules.yaml").write_text(_yaml_rule("placed", ">=", "'2024-05-01'"))
        result = runner.invoke(app, ["validate", "rules.yaml", "--schema", "models.py:Order"])
        assert result.exit_code == 0, result.output

    def test_evaluate_refuses_a_value_that_does_not_fit(self, project: Path):
        (project / "rules.yaml").write_text(_yaml_rule("amount", ">", "'100.1'"))
        (project / "fact.json").write_text(json.dumps({"amount": 200.0}))
        result = runner.invoke(
            app, ["evaluate", "rules.yaml", "fact.json", "--schema", "models.py:Order"]
        )
        assert result.exit_code == 1
        assert "Write 100.1 without quotes" in result.output

    def test_config_file_on_off_settings_need_true_or_false(self, project: Path):
        (project / "rules.yaml").write_text(_yaml_rule("amount", ">", "1"))
        (project / "fact.json").write_text(json.dumps({"amount": 200.0}))
        (project / "cfg.yaml").write_text("strict_type_comparison: yes\n")
        result = runner.invoke(app, ["evaluate", "rules.yaml", "fact.json", "--config", "cfg.yaml"])
        assert result.exit_code == 2
        assert "strict_type_comparison must be true or false, got 'yes'" in result.output


class TestCliValidateSettings:
    def test_validate_follows_the_config_files_coercion(self, project: Path):
        (project / "flags.py").write_text(
            "from pydantic import BaseModel\n\n\nclass Flags(BaseModel):\n    active: bool\n"
        )
        (project / "rules.yaml").write_text(_yaml_rule("active", "==", "'true'"))
        args = ["validate", "rules.yaml", "--schema", "flags.py:Flags"]
        assert runner.invoke(app, args).exit_code == 1
        (project / "cfg.yaml").write_text("boolean_string_coercion: true\n")
        result = runner.invoke(app, [*args, "--config", "cfg.yaml"])
        assert result.exit_code == 0, result.output

    def test_validate_still_shows_other_warnings(self, project: Path):
        from fluxrules import MembershipValueWarning

        (project / "rules.yaml").write_text(_yaml_rule("country", "in", "US"))
        with pytest.warns(MembershipValueWarning):
            result = runner.invoke(app, ["validate", "rules.yaml"])
        assert result.exit_code == 0, result.output
