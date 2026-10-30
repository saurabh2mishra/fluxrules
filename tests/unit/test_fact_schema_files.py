"""Fact schemas named by import string: load_schema, rule files, YAML loader, CLI."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fluxrules import UnknownFieldError
from fluxrules.adapters.loaders.rule_file import parse_rule_document, read_rule_file
from fluxrules.adapters.loaders.yaml_loader import load_rules_from_yaml
from fluxrules.cli.main import app
from fluxrules.facts import load_schema, schema_info

runner = CliRunner()

MODELS = textwrap.dedent(
    """
    from pydantic import BaseModel, ConfigDict

    from fluxrules.facts import lenient_aliases


    class Account(BaseModel):
        model_config = ConfigDict(alias_generator=lenient_aliases())

        age_days: int
        country: str


    class Payment(BaseModel):
        amount: float
        account: Account


    NOT_A_MODEL = 42
    """
)


def _rule(field: str, name: str = "r1", rid: int = 1) -> dict:
    return {
        "id": rid,
        "name": name,
        "action": "review",
        "conditions": {"type": "condition", "field": field, "op": ">", "value": 1},
    }


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project root (the cwd) with an importable ``shop_models`` package."""
    pkg = tmp_path / "shop_models"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(MODELS)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FLUXRULES_CONFIG_FILE", raising=False)
    # The CLI also searches ~/.fluxrules.yaml; keep a real one out of the tests.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    yield tmp_path
    sys.modules.pop("shop_models", None)


def _yaml(path: Path, data: object) -> Path:
    yaml = pytest.importorskip("yaml")
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


# load_schema


class TestLoadSchema:
    def test_module_form_searches_cwd(self, project: Path) -> None:
        model = load_schema("shop_models:Payment")
        assert model.__name__ == "Payment"
        assert "account.age_days" in schema_info(model).fields

    def test_cwd_is_not_left_on_sys_path(self, project: Path) -> None:
        before = list(sys.path)
        load_schema("shop_models:Payment")
        assert sys.path == before

    def test_file_form_relative_to_base_dir(self, tmp_path: Path) -> None:
        (tmp_path / "models.py").write_text(MODELS)
        model = load_schema("models.py:Payment", base_dir=tmp_path)
        assert set(schema_info(model).fields) == {"amount", "account.age_days", "account.country"}

    def test_file_form_with_directory(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "schemas.py").write_text(MODELS)
        assert load_schema("app/schemas.py:Account", base_dir=tmp_path).__name__ == "Account"

    @pytest.mark.parametrize("spec", ["shop_models", "shop_models:", ":Payment"])
    def test_malformed_spec(self, project: Path, spec: str) -> None:
        with pytest.raises(ImportError, match="must look like"):
            load_schema(spec)

    def test_missing_module(self, project: Path) -> None:
        with pytest.raises(ImportError, match="cannot import fact schema module"):
            load_schema("no_such_module_xyz:Payment")

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ImportError, match="not found"):
            load_schema("missing.py:Payment", base_dir=tmp_path)

    def test_missing_class(self, project: Path) -> None:
        with pytest.raises(ImportError, match="has no class 'Order'"):
            load_schema("shop_models:Order")

    def test_not_a_model(self, project: Path) -> None:
        with pytest.raises(TypeError, match="fact_schema must be"):
            load_schema("shop_models:NOT_A_MODEL")


class TestUnknownFields:
    def test_collects_every_unknown_field(self, project: Path) -> None:
        info = schema_info(load_schema("shop_models:Payment"))
        rules = [_rule("amount"), _rule("account.ageDays", "r2", 2), _rule("amout", "r3", 3)]
        errors = info.unknown_fields(rules)
        assert [(e.rule, e.field, e.suggestion) for e in errors] == [
            ("r2", "account.ageDays", "account.age_days"),
            ("r3", "amout", "amount"),
        ]
        assert "Known fields" not in errors[0].summary
        assert "Did you mean 'account.age_days'?" in errors[0].summary

    def test_check_rules_still_raises_first(self, project: Path) -> None:
        info = schema_info(load_schema("shop_models:Payment"))
        with pytest.raises(UnknownFieldError, match="amout"):
            info.check_rules([_rule("amout"), _rule("account.ageDays", "r2", 2)])


# Rule files


class TestRuleFile:
    def test_document_form(self) -> None:
        doc = parse_rule_document({"fact_schema": "m:Payment", "rules": [_rule("amount")]})
        assert doc.fact_schema == "m:Payment"
        assert doc.rules[0]["name"] == "r1"

    def test_list_and_single_forms_have_no_schema(self) -> None:
        assert parse_rule_document([_rule("amount")]).fact_schema is None
        assert len(parse_rule_document(_rule("amount")).rules) == 1
        assert parse_rule_document(None).rules == []

    @pytest.mark.parametrize(
        ("data", "message"),
        [
            ({"rules": [], "extra": 1}, "unexpected top-level keys"),
            ({"rules": {"id": 1}}, "must be a list"),
            ({"rules": [], "fact_schema": ["x"]}, "import string"),
            ("just a string", "expected a rule mapping"),
        ],
    )
    def test_bad_shapes(self, data: object, message: str) -> None:
        with pytest.raises(ValueError, match=message):
            parse_rule_document(data)

    def test_json_file(self, tmp_path: Path) -> None:
        path = tmp_path / "rules.json"
        path.write_text(json.dumps({"fact_schema": "m:P", "rules": [_rule("amount")]}))
        assert read_rule_file(path).fact_schema == "m:P"


class TestYamlLoaderSchema:
    def test_file_declared_schema_is_checked(self, project: Path) -> None:
        path = _yaml(
            project / "rules.yaml",
            {"fact_schema": "shop_models:Payment", "rules": [_rule("account.ageDays")]},
        )
        with pytest.raises(UnknownFieldError, match="account.age_days"):
            load_rules_from_yaml(str(path), trust_schema=True)

    def test_file_declared_schema_needs_trust(self, project: Path) -> None:
        path = _yaml(
            project / "rules.yaml",
            {"fact_schema": "shop_models:Payment", "rules": [_rule("amount")]},
        )
        with pytest.raises(ValueError, match="trust_schema=True"):
            load_rules_from_yaml(str(path))
        # Naming the schema yourself needs no trust flag.
        assert load_rules_from_yaml(str(path), fact_schema="shop_models:Payment")

    def test_declared_file_path_resolves_next_to_the_rules(self, tmp_path: Path) -> None:
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "models.py").write_text(MODELS)
        path = _yaml(
            rules_dir / "payments.yaml",
            {"fact_schema": "models.py:Payment", "rules": [_rule("account.country")]},
        )
        assert load_rules_from_yaml(str(path), trust_schema=True)[0]["name"] == "r1"

    def test_argument_overrides_file(self, project: Path) -> None:
        path = _yaml(
            project / "rules.yaml",
            {"fact_schema": "shop_models:Payment", "rules": [_rule("age_days")]},
        )
        # age_days is a field of Account, not Payment.
        assert load_rules_from_yaml(str(path), fact_schema="shop_models:Account")
        from shop_models import Account

        assert load_rules_from_yaml(str(path), fact_schema=Account)

    def test_plain_list_is_unchecked(self, project: Path) -> None:
        path = _yaml(project / "rules.yaml", [_rule("anything")])
        assert len(load_rules_from_yaml(str(path))) == 1


# CLI


def _validate(*args: str):
    result = runner.invoke(app, ["validate", *args])
    payload = json.loads(result.stdout) if result.stdout.strip().startswith("{") else None
    return result, payload


class TestCliValidate:
    def test_schema_flag_reports_every_unknown_field(self, project: Path) -> None:
        path = _yaml(
            project / "rules.yaml",
            [_rule("account.ageDays"), _rule("amout", "r2", 2), _rule("amount", "r3", 3)],
        )
        result, payload = _validate(str(path), "--schema", "shop_models:Payment")
        assert result.exit_code == 1
        assert payload["valid"] is False
        assert len(payload["issues"]) == 2
        assert "Did you mean 'account.age_days'?" in payload["issues"][0]
        assert payload["schemas"] == [
            {"file": str(path), "fact_schema": "shop_models:Payment", "source": "--schema"}
        ]

    def test_clean_rules_exit_zero(self, project: Path) -> None:
        path = _yaml(project / "rules.yaml", [_rule("account.age_days")])
        result, payload = _validate(str(path), "--schema", "shop_models:Payment")
        assert result.exit_code == 0
        assert payload["valid"] is True

    def test_schema_from_rule_file(self, project: Path) -> None:
        path = _yaml(
            project / "rules.yaml",
            {"fact_schema": "shop_models:Payment", "rules": [_rule("amout")]},
        )
        result, payload = _validate(str(path), "--trust-schema")
        assert result.exit_code == 1
        assert payload["schemas"][0]["source"] == f"rule file {path}"

    def test_schema_from_rule_file_needs_trust(self, project: Path) -> None:
        (project / "evil.py").write_text("raise SystemExit('ran untrusted code')\n")
        path = _yaml(project / "rules.yaml", {"fact_schema": "evil.py:X", "rules": [_rule("a")]})
        result = runner.invoke(app, ["validate", str(path)])
        assert result.exit_code == 2
        assert "--trust-schema" in result.stderr
        assert "ran untrusted code" not in result.output

    def test_schema_from_found_config_needs_trust(self, project: Path) -> None:
        (project / "fluxrules.yaml").write_text("fact_schema: shop_models:Payment\n")
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result = runner.invoke(app, ["validate", str(path)])
        assert result.exit_code == 2
        assert "config fluxrules.yaml names fact_schema" in result.stderr

    def test_schema_from_default_config(self, project: Path) -> None:
        (project / "fluxrules.yaml").write_text("fact_schema: shop_models:Payment\n")
        path = _yaml(project / "rules.yaml", [_rule("amout")])
        result, payload = _validate(str(path), "--trust-schema")
        assert result.exit_code == 1
        assert payload["schemas"][0]["source"] == "config fluxrules.yaml"

    def test_explicit_config_with_file_form(self, project: Path) -> None:
        conf = project / "conf"
        conf.mkdir()
        (conf / "models.py").write_text(MODELS)
        (conf / "settings.yaml").write_text("fact_schema: models.py:Payment\n")
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result, payload = _validate(str(path), "--config", str(conf / "settings.yaml"))
        assert result.exit_code == 0
        assert payload["schemas"][0]["fact_schema"] == "models.py:Payment"

    def test_precedence_flag_then_rule_file_then_config(self, project: Path) -> None:
        (project / "fluxrules.yaml").write_text("fact_schema: shop_models:Account\n")
        declared = _yaml(
            project / "declared.yaml",
            {"fact_schema": "shop_models:Payment", "rules": [_rule("amount")]},
        )
        plain = _yaml(project / "plain.yaml", [_rule("age_days", "r2", 2)])

        _, payload = _validate(str(declared), str(plain), "--trust-schema")
        assert [s["fact_schema"] for s in payload["schemas"]] == [
            "shop_models:Payment",
            "shop_models:Account",
        ]

        _, payload = _validate(str(declared), str(plain), "--schema", "shop_models:Account")
        assert {s["source"] for s in payload["schemas"]} == {"--schema"}
        # With several files, issues name their file.
        assert payload["issues"][0].startswith(f"{declared}: ")

    def test_no_schema_keeps_structural_validation_only(self, project: Path) -> None:
        path = _yaml(project / "rules.yaml", [_rule("anything")])
        result, payload = _validate(str(path))
        assert result.exit_code == 0
        assert payload["schemas"] == [{"file": str(path), "fact_schema": None, "source": None}]

    def test_structural_issue_exits_one(self, project: Path) -> None:
        path = _yaml(project / "rules.yaml", [_rule("amount"), _rule("amount", "dup", 1)])
        result, payload = _validate(str(path))
        assert result.exit_code == 1
        assert payload["valid"] is False

    @pytest.mark.parametrize(
        "spec", ["shop_models:Nope", "nowhere_xyz:Payment", "bad-spec", "shop_models:NOT_A_MODEL"]
    )
    def test_unloadable_schema_exits_two(self, project: Path, spec: str) -> None:
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result = runner.invoke(app, ["validate", str(path), "--schema", spec])
        assert result.exit_code == 2
        assert "Cannot load fact schema" in result.stderr

    def test_missing_config_exits_two(self, project: Path) -> None:
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result = runner.invoke(app, ["validate", str(path), "--config", "nope.yaml"])
        assert result.exit_code == 2

    def test_unreadable_rules_exit_two(self, project: Path) -> None:
        (project / "rules.yaml").write_text("rules: {id: 1}\n")
        result = runner.invoke(app, ["validate", str(project / "rules.yaml")])
        assert result.exit_code == 2
        assert "Cannot load rules" in result.stderr


class TestCliEvaluate:
    def _files(self, project: Path, field: str = "amount") -> tuple[str, str]:
        rules = _yaml(project / "rules.yaml", [_rule(field)])
        event = project / "event.json"
        event.write_text(json.dumps({"amount": 5, "account": {"ageDays": "5", "country": "US"}}))
        return str(rules), str(event)

    def test_unknown_field_refused(self, project: Path) -> None:
        rules, event = self._files(project, "amout")
        result = runner.invoke(app, ["evaluate", rules, event, "--schema", "shop_models:Payment"])
        assert result.exit_code == 1
        assert "Did you mean 'amount'?" in result.stderr

    def test_validate_facts_normalizes_nested_event(self, project: Path) -> None:
        rules, event = self._files(project, "account.age_days")
        args = ["evaluate", rules, event, "--format", "json", "--schema", "shop_models:Payment"]
        # Raw, the event is nested: a clean error, not a traceback.
        raw = runner.invoke(app, args)
        assert raw.exit_code == 1
        assert "account.age_days" in raw.stderr
        # Normalized: flattened, ageDays renamed and "5" coerced, so 5 > 1 matches.
        result = runner.invoke(app, [*args, "--validate-facts", "normalize"])
        assert result.exit_code == 0
        assert json.loads(result.stdout)["matched_rules"][0]["name"] == "r1"

    def test_invalid_event_exits_one(self, project: Path) -> None:
        rules, _ = self._files(project)
        bad = project / "bad.json"
        bad.write_text(json.dumps({"amount": "lots"}))
        result = runner.invoke(
            app,
            [
                "evaluate",
                rules,
                str(bad),
                "--schema",
                "shop_models:Payment",
                "--validate-facts",
                "strict",
            ],
        )
        assert result.exit_code == 1
        assert "does not match fact schema" in result.stderr

    def test_validate_facts_needs_schema(self, project: Path) -> None:
        rules, event = self._files(project)
        result = runner.invoke(app, ["evaluate", rules, event, "--validate-facts", "normalize"])
        assert result.exit_code == 2

    def test_bad_validate_facts_value(self, project: Path) -> None:
        rules, event = self._files(project)
        result = runner.invoke(app, ["evaluate", rules, event, "--validate-facts", "loose"])
        assert result.exit_code == 2


def test_init_writes_commented_fact_schema(tmp_path: Path) -> None:
    runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert "# fact_schema: myapp.models:Order" in (tmp_path / "fluxrules.yaml").read_text()


class TestCliConfigAndErrors:
    def test_config_not_read_when_schema_is_given(self, project: Path) -> None:
        (project / "fluxrules.yaml").write_text("fact_schema: [not: valid\n")
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result = runner.invoke(app, ["validate", str(path), "--schema", "shop_models:Payment"])
        assert result.exit_code == 0
        assert "Ignoring" not in result.stderr

    def test_unreadable_implicit_config_is_ignored_with_a_note(self, project: Path) -> None:
        (project / "fluxrules.yaml").write_text("fact_schema: [not: valid\n")
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result = runner.invoke(app, ["validate", str(path)])
        assert result.exit_code == 0
        assert "Ignoring fluxrules.yaml" in result.stderr

    def test_implicit_config_without_pyyaml_is_ignored(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (project / "fluxrules.yaml").write_text("fact_schema: shop_models:Payment\n")
        rules = project / "rules.json"
        rules.write_text(json.dumps([_rule("amount")]))
        monkeypatch.setitem(sys.modules, "yaml", None)  # PyYAML not installed
        result = runner.invoke(app, ["validate", str(rules)])
        assert result.exit_code == 0
        assert "Ignoring fluxrules.yaml" in result.stderr

    def test_unreadable_explicit_config_fails(self, project: Path) -> None:
        (project / "conf.yaml").write_text("fact_schema: [not: valid\n")
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result = runner.invoke(app, ["validate", str(path), "--config", "conf.yaml"])
        assert result.exit_code == 2
        assert "cannot read config file" in result.stderr

    def test_schema_module_with_syntax_error_exits_two(self, project: Path) -> None:
        (project / "broken.py").write_text("class Payment(:\n")
        path = _yaml(project / "rules.yaml", [_rule("amount")])
        result = runner.invoke(app, ["validate", str(path), "--schema", "broken.py:Payment"])
        assert result.exit_code == 2
        assert "SyntaxError" in result.stderr

    def test_engine_that_cannot_take_the_schema_exits_two(self, project: Path) -> None:
        (project / "attrs_like.py").write_text(
            "class _F:\n    def __init__(self, name):\n        self.name = name\n\n"
            "class Thing:\n    __attrs_attrs__ = (_F('amount'),)\n"
            "    __annotations__ = {'amount': int}\n"
        )
        rules = _yaml(project / "rules.yaml", [_rule("amount")])
        event = project / "event.json"
        event.write_text(json.dumps({"amount": 5}))
        result = runner.invoke(
            app,
            [
                "evaluate",
                str(rules),
                str(event),
                "--schema",
                "attrs_like.py:Thing",
                "--validate-facts",
                "normalize",
            ],
        )
        assert result.exit_code == 2
        assert "Cannot build engine" in result.stderr


class TestSharedConfigLookup:
    def test_cli_finds_home_config_like_deployment_config(self, project: Path) -> None:
        from fluxrules.config.deployment import find_config_file

        home = project / "home"
        home.mkdir()
        (home / ".fluxrules.yaml").write_text("fact_schema: shop_models:Payment\n")
        assert find_config_file() == home / ".fluxrules.yaml"
        path = _yaml(project / "rules.yaml", [_rule("amout")])
        result, payload = _validate(str(path), "--trust-schema")
        assert result.exit_code == 1
        assert payload["schemas"][0]["source"] == f"config {home / '.fluxrules.yaml'}"

    def test_unknown_suffix_is_read_as_json(self, tmp_path: Path) -> None:
        from fluxrules.config.deployment import read_config_file

        path = tmp_path / "settings.conf"
        path.write_text(json.dumps({"fact_schema": "m:X"}))
        assert read_config_file(path) == {"fact_schema": "m:X"}
