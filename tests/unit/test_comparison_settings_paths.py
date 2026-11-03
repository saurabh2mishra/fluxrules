"""The comparison settings reach every evaluation path.

``strict_null_handling``, ``strict_type_comparison``, ``boolean_string_coercion``
and ``missing_field`` used to be ignored in three places: the alpha prefilter
ignored coercion, the reference evaluator (``fluxrules.evaluate()`` and the
HTTP API) ignored the first three, and ``fluxrules evaluate`` applied none of
them from its config file. ``tests/engine/test_comparison_matrix.py`` proves the
paths agree in general; these tests pin each fix on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fluxrules import F, Rule, evaluate
from fluxrules.domain.conditions.evaluator import evaluate_conditions
from fluxrules.engine.configuration import EngineConfig, get_config, set_config
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.prefilter import PredicateIndex

TRUE_RULE = Rule(id=1, name="flag_true", conditions=F("flag") == True, action="hit")  # noqa: E712


@pytest.fixture
def process_config():
    """Set the process-wide config for one test, then restore it."""
    old = get_config()
    yield set_config
    set_config(old)


class TestPrefilterAppliesCoercion:
    def test_the_prefilter_is_engaged_for_this_rule(self):
        engine = PhreakEngine()
        engine.load_rules([TRUE_RULE])
        assert engine._alpha_engage and engine._alpha_index is not None

    @pytest.mark.parametrize("text", ["true", "True", " TRUE "])
    def test_true_string_matches_true_with_coercion(self, text):
        engine = PhreakEngine(config=EngineConfig(boolean_string_coercion=True))
        engine.load_rules([TRUE_RULE])
        assert engine.evaluate({"flag": text}).fired_rules == [1]

    def test_without_coercion_the_string_still_does_not_match(self):
        engine = PhreakEngine()
        engine.load_rules([TRUE_RULE])
        assert engine.evaluate({"flag": "true"}).fired_rules == []

    def test_turning_coercion_on_after_load_applies_at_the_next_evaluation(self):
        config = EngineConfig()
        engine = PhreakEngine(config=config)
        engine.load_rules([TRUE_RULE])
        assert engine.evaluate({"flag": "true"}).fired_rules == []
        config.boolean_string_coercion = True
        assert engine.evaluate({"flag": "true"}).fired_rules == [1]

    def test_rule_side_string_is_coerced_too(self):
        rule = Rule(id=1, name="r", conditions=F("flag") == "true", action="hit")
        engine = PhreakEngine(config=EngineConfig(boolean_string_coercion=True))
        engine.load_rules([rule])
        assert engine.evaluate({"flag": True}).fired_rules == [1]

    def test_index_prunes_with_and_without_coercion(self):
        index = PredicateIndex.from_rules([TRUE_RULE])
        assert index.prune({"flag": "true"}, [1]) == []
        assert index.prune({"flag": "true"}, [1], coerce_bool_strings=True) == [1]
        assert index.candidate_rule_ids({"flag": "false"}, [1], coerce_bool_strings=True) == set()


class TestReferenceEvaluatorReadsSettings:
    """``fluxrules.evaluate()`` and the HTTP API follow the process-wide config."""

    def test_strict_type_comparison(self, process_config):
        rule = Rule(id=1, name="r", conditions=F("count") == 1, action="hit")
        assert evaluate(rule, {"count": True}).fired_rules == [1]
        process_config(EngineConfig(strict_type_comparison=True))
        assert evaluate(rule, {"count": True}).fired_rules == []

    def test_strict_null_handling(self, process_config):
        rule = Rule(id=1, name="r", conditions=F("v") == None, action="hit")  # noqa: E711
        assert evaluate(rule, {"v": None}).fired_rules == []
        process_config(EngineConfig(strict_null_handling=True))
        assert evaluate(rule, {"v": None}).fired_rules == [1]

    def test_boolean_string_coercion(self, process_config):
        assert evaluate(TRUE_RULE, {"flag": "true"}).fired_rules == []
        process_config(EngineConfig(boolean_string_coercion=True))
        assert evaluate(TRUE_RULE, {"flag": "true"}).fired_rules == [1]

    def test_raw_condition_dicts_follow_the_config(self, process_config):
        condition = TRUE_RULE.conditions
        assert evaluate_conditions(condition, {"flag": "true"}) is False
        process_config(EngineConfig(boolean_string_coercion=True))
        assert evaluate_conditions(condition, {"flag": "true"}) is True


pytest.importorskip("typer")

from typer.testing import CliRunner  # noqa: E402

from fluxrules.cli.main import app  # noqa: E402

runner = CliRunner()


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with a rule file and no config found elsewhere."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FLUXRULES_CONFIG_FILE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "rules.json").write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "name": "flag_true",
                    "action": "hit",
                    "conditions": {"type": "condition", "field": "flag", "op": "==", "value": True},
                },
                {
                    "id": 2,
                    "name": "not_blocked",
                    "action": "allow",
                    "conditions": {
                        "type": "not",
                        "condition": {
                            "type": "condition",
                            "field": "blocked",
                            "op": "==",
                            "value": True,
                        },
                    },
                },
            ]
        )
    )
    (tmp_path / "fact.json").write_text(json.dumps({"flag": "true"}))
    return tmp_path


def _matched(*args: str) -> list[int]:
    result = runner.invoke(app, ["evaluate", "rules.json", "fact.json", "--format", "json", *args])
    assert result.exit_code == 0, result.output
    return [r["id"] for r in json.loads(result.stdout)["matched_rules"]]


class TestCliAppliesConfigSettings:
    def test_defaults_without_a_config_file(self, project):
        # "true" is not True, and NOT over the missing `blocked` field fires.
        assert _matched() == [2]

    def test_settings_from_an_explicit_config(self, project):
        (project / "settings.yaml").write_text(
            "boolean_string_coercion: true\nmissing_field: unknown\n"
        )
        assert _matched("--config", "settings.yaml") == [1]

    def test_settings_from_a_config_found_automatically(self, project):
        (project / "fluxrules.yaml").write_text("boolean_string_coercion: true\n")
        assert sorted(_matched()) == [1, 2]

    def test_yaml_false_for_missing_field_means_the_string_false(self, project):
        (project / "fluxrules.yaml").write_text("missing_field: false\n")
        assert _matched() == [2]

    def test_the_file_fluxrules_init_writes_keeps_the_defaults(self, project):
        result = runner.invoke(app, ["init", "--dir", str(project / "new")])
        assert result.exit_code == 0, result.output
        config = project / "new" / "fluxrules.yaml"
        assert "boolean_string_coercion: false" in config.read_text()
        assert "use_optimized_engine" not in config.read_text(), "nothing reads it"
        assert _matched("--config", str(config)) == [2]

    def test_a_bad_value_in_an_explicit_config_fails(self, project):
        (project / "settings.yaml").write_text("strict_type_comparison: yes please\n")
        result = runner.invoke(
            app, ["evaluate", "rules.json", "fact.json", "--config", "settings.yaml"]
        )
        assert result.exit_code != 0
        assert "strict_type_comparison must be true or false" in " ".join(result.output.split())

    def test_a_bad_value_in_a_found_config_is_reported_and_ignored(self, project):
        (project / "fluxrules.yaml").write_text("missing_field: maybe\n")
        result = runner.invoke(app, ["evaluate", "rules.json", "fact.json", "--format", "json"])
        assert result.exit_code == 0
        assert "missing_field must be 'false', 'unknown' or null" in " ".join(result.stderr.split())
        assert [r["id"] for r in json.loads(result.stdout)["matched_rules"]] == [2]


class _DocumentedCustomEngine:
    """Built lazily: the custom engine docs/custom-engines.md shows, with no ``config``."""

    @staticmethod
    def build():
        from fluxrules.engine.base import BaseEngine

        class FirstMatch(BaseEngine):
            def _evaluate_rules(self, rule_ids, facts):
                fired, actions, why = [], [], {}
                for rule_id in rule_ids:
                    rule = self.rule_repository.get(rule_id)
                    if rule and evaluate_conditions(rule.conditions, facts):
                        fired.append(rule_id)
                        actions.extend(rule.actions)
                        why[rule_id] = "matched"
                return fired, actions, why

        return FirstMatch


@pytest.fixture
def custom_engine():
    from fluxrules.engine import register_engine, unregister_engine

    register_engine("DOCS_CUSTOM", _DocumentedCustomEngine.build())
    yield "DOCS_CUSTOM"
    unregister_engine("DOCS_CUSTOM")


class TestCliSettingsReachCustomEngines:
    """A registered BaseEngine subclass takes no ``config``; settings still apply."""

    @pytest.mark.parametrize(
        ("config_text", "flag_rule_fires"),
        [
            (None, False),
            ("strict_null_handling: false\nstrict_type_comparison: false\n", False),
            ("boolean_string_coercion: true\n", True),
        ],
        ids=["no config", "fluxrules init defaults", "coercion on"],
    )
    def test_custom_engine_runs_and_honours_settings(
        self, project, custom_engine, config_text, flag_rule_fires
    ):
        # Only rule 1 (flag == True on the string "true") is checked: a
        # BaseEngine subclass does not fire NOT over a missing field the way
        # PhreakEngine does, which is unrelated to the config file.
        if config_text is not None:
            (project / "fluxrules.yaml").write_text(config_text)
        assert (1 in _matched("--engine", custom_engine)) is flag_rule_fires

    def test_the_process_config_is_restored_after_the_command(self, project):
        before = get_config()
        (project / "fluxrules.yaml").write_text("boolean_string_coercion: true\n")
        _matched()
        assert get_config() is before
