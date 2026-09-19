"""One authoring type, and the deprecations that got us there.

Three different classes named ``Rule`` were once importable from three
different modules:

* ``fluxrules.Rule``                        - the canonical Pydantic model
* ``fluxrules.domain.models.Rule``          - the low-level frozen dataclass
* ``fluxrules.engine.infrastructure.Rule``  - the engine's runtime dataclass

An import that looked obviously correct could silently bind the wrong class,
and that is exactly how a shipped README example ended up broken. The latter
two were renamed to ``EngineRule`` and ``RuntimeRule``; ``RuntimeRule`` has
since been removed entirely, because production code never constructed one.

These tests pin the contract that resulted:

1. Exactly one class is named ``Rule``, and it is the Pydantic model.
2. It is the only type a user ever constructs.
3. ``EngineRule`` remains an internal/persistence type, not an authoring one.
4. The removed names keep working - loudly - for one release.
"""

from __future__ import annotations

import warnings

import pytest

from fluxrules import PhreakEngine

_DEPRECATION_MATCH = "deprecated"


def _leaf(field: str = "a", op: str = ">", value: object = 1) -> dict:
    return {"type": "condition", "field": field, "op": op, "value": value}


class TestCanonicalRule:
    """Exactly one importable ``Rule``, and it is the Pydantic one."""

    def test_top_level_rule_is_the_pydantic_model(self):
        from fluxrules import Rule
        from fluxrules.domain.unified_rule import Rule as Canonical

        assert Rule is Canonical

    def test_domain_rule_is_the_same_object(self):
        from fluxrules import Rule as TopLevel
        from fluxrules.domain import Rule as DomainRule

        assert DomainRule is TopLevel

    def test_domain_models_no_longer_exports_rule(self):
        """The low-level dataclass is ``EngineRule`` now."""
        import fluxrules.domain.models as models

        assert not hasattr(models, "Rule")
        assert hasattr(models, "EngineRule")


class TestSingleAuthoringGate:
    """Phase 3b: exactly one type a user is ever expected to construct."""

    def test_engine_rule_is_not_top_level_public_api(self):
        """``EngineRule`` is internal. It must not be an authoring option.

        It stays importable from ``domain.models`` because it appears in the
        published ``RulePersistencePort`` signature, but it must never be
        something a user reaches for by default.
        """
        import fluxrules

        assert "EngineRule" not in fluxrules.__all__
        assert not hasattr(fluxrules, "EngineRule")

    def test_rule_is_the_only_top_level_rule_name(self):
        import fluxrules

        rule_names = {n for n in fluxrules.__all__ if n.endswith("Rule")}
        assert rule_names == {"Rule"}

    def test_repository_holds_exactly_one_type(self):
        """Phase 1c: normalisation on ingest.

        Previously the repository stored whatever it was handed, so two
        classes could coexist in one repository and engines duck-typed across
        them.
        """
        from fluxrules import Rule
        from fluxrules.engine.infrastructure import GlobalRuleRepository

        repo = GlobalRuleRepository()
        repo.add_rule(Rule(id=1, name="a", condition_dsl=_leaf(), persist=False))
        repo.add_rule({"id": 2, "name": "b", "condition_dsl": _leaf()})

        stored = {type(r) for r in repo.rules.values()}
        assert stored == {Rule}

    def test_normalising_a_dict_never_persists(self):
        """Normalisation must not trigger ``Rule``'s persistence hook."""
        from fluxrules.engine.infrastructure import normalize_rule

        rule = normalize_rule({"id": 3, "name": "c", "condition_dsl": _leaf()})
        assert rule.persist is False

    def test_persisted_condition_lists_become_a_real_dsl_tree(self):
        """The ORM's list-of-conditions shape must be *converted*, not tolerated.

        ``domain_rule_to_orm`` stores an ``EngineRule``'s conditions as a bare
        list of ``{fact, operator, value}`` dicts. The engines only traverse
        DSL trees, so such a rule used to load without error and then match
        nothing at all - the tolerant path preserved a silent failure. It is
        now converted to an equivalent DSL tree on the way in.
        """
        from fluxrules.engine.infrastructure import normalize_rule

        rule = normalize_rule(
            {
                "id": 4,
                "name": "orm-shaped",
                "condition_dsl": [{"fact": "a", "operator": "gt", "value": 1}],
            }
        )

        assert rule.id == 4
        assert rule.condition_dsl == {
            "type": "condition",
            "field": "a",
            "op": "gt",
            "value": 1,
        }

    def test_persisted_condition_lists_are_an_implicit_and(self):
        from fluxrules.engine.infrastructure import normalize_rule

        rule = normalize_rule(
            {
                "id": 5,
                "name": "two-conditions",
                "condition_dsl": [
                    {"fact": "a", "operator": "gt", "value": 1},
                    {"fact": "b", "operator": "eq", "value": "x"},
                ],
            }
        )

        assert rule.condition_dsl["type"] == "and"
        assert [child["field"] for child in rule.condition_dsl["children"]] == [
            "a",
            "b",
        ]

    @pytest.mark.parametrize("cls", [PhreakEngine], ids=["PHREAK"])
    def test_a_persisted_rule_actually_fires(self, cls):
        """The behavioural point of the conversion."""
        from fluxrules.domain.models import EngineRule, RuleCondition

        engine_rule = EngineRule(
            id=9,
            name="from-db",
            conditions=(RuleCondition("a", "gt", 1),),
            actions=("flag",),
        )
        engine = cls()
        engine.load_rules([engine_rule])

        assert engine.evaluate({"a": 5}).fired_rules == [9]
        assert engine.evaluate({"a": 5}).actions == ["flag"]
        assert engine.evaluate({"a": 0}).fired_rules == []

    def test_authored_dsl_dicts_are_untouched(self):
        """Conversion must not perturb the shape users actually author."""
        from fluxrules.engine.infrastructure import normalize_rule

        authored = _leaf()
        rule = normalize_rule({"id": 6, "name": "authored", "condition_dsl": authored})

        assert rule.condition_dsl == authored

    @pytest.mark.parametrize("cls", [PhreakEngine], ids=["PHREAK"])
    def test_string_ids_still_work(self, cls):
        """Why the unvalidated fallback has to stay.

        ``Rule.id`` is typed ``int``, but engines only use the id as an opaque
        key, so string-keyed rules evaluate end to end. Documented examples use
        them. Validation would reject these, so normalisation falls back to
        unvalidated construction rather than breaking working rules.
        """
        engine = cls()
        engine.load_rules(
            [
                {
                    "id": "rule_1",
                    "name": "string-keyed",
                    "condition_dsl": _leaf(),
                    "action": "flag",
                }
            ]
        )

        assert engine.evaluate({"a": 5}).fired_rules == ["rule_1"]
        assert engine.evaluate({"a": 5}).actions == ["flag"]


class TestMultiAction:
    """Phase 1a: ``Rule`` can express everything a stored rule can."""

    def test_actions_defaults_from_singular_action(self):
        from fluxrules import Rule

        rule = Rule(name="r", condition_dsl=_leaf(), action="go", persist=False)
        assert rule.actions == ("go",)

    def test_singular_action_mirrors_first_of_actions(self):
        from fluxrules import Rule

        rule = Rule(name="r", condition_dsl=_leaf(), actions=("a", "b"), persist=False)
        assert rule.action == "a"
        assert rule.actions == ("a", "b")

    def test_conflicting_action_and_actions_is_rejected(self):
        """Silently picking one would be the exact bug this work removes."""
        from pydantic import ValidationError

        from fluxrules import Rule

        with pytest.raises(ValidationError, match="Conflicting actions"):
            Rule(
                name="r",
                condition_dsl=_leaf(),
                action="x",
                actions=("y", "z"),
                persist=False,
            )

    def test_multi_action_survives_engine_rule_round_trip(self):
        """The data-loss bug: collapsing to a single action on conversion."""
        from fluxrules import Rule

        rule = Rule(
            name="r",
            condition_dsl=_leaf(),
            actions=("escalate", "notify"),
            persist=False,
        )
        engine_rule = rule.to_engine_rule()
        assert engine_rule.actions == ("escalate", "notify")

        back = Rule.from_engine_rule(engine_rule)
        assert back.actions == ("escalate", "notify")

    def test_from_engine_rule_reconstructs_a_conjunctive_dsl(self):
        from fluxrules import Rule
        from fluxrules.domain.models import EngineRule, RuleCondition

        engine_rule = EngineRule(
            id=1,
            name="r",
            conditions=(
                RuleCondition(fact="a", operator=">", value=1),
                RuleCondition(fact="b", operator="<", value=2),
            ),
            actions=("go",),
        )
        rule = Rule.from_engine_rule(engine_rule)
        # An EngineRule built from a flat conjunction now carries the
        # authoritative ``and`` tree (the canonical conjunctive shape produced
        # by ``conditions_to_dsl``); ``from_engine_rule`` passes it through.
        assert rule.condition_dsl["type"] == "and"
        assert len(rule.condition_dsl["children"]) == 2

    def test_from_engine_rule_does_not_persist_by_default(self):
        """It converts something already in storage; re-persisting duplicates."""
        from fluxrules import Rule
        from fluxrules.domain.models import EngineRule, RuleCondition

        engine_rule = EngineRule(
            id=9,
            name="r",
            conditions=(RuleCondition(fact="a", operator=">", value=1),),
        )
        assert Rule.from_engine_rule(engine_rule).persist is False

    @pytest.mark.parametrize("engine_type", ["PHREAK"])
    def test_engines_fire_every_action(self, engine_type):
        """The engine previously emitted only the first action."""
        from fluxrules import Rule
        from fluxrules.engine import get_engine

        engine = get_engine(engine_type)
        engine.load_rules(
            [
                Rule(
                    id=1,
                    name="adult",
                    condition_dsl=_leaf("age", ">=", 18),
                    actions=("allow", "audit"),
                    persist=False,
                )
            ]
        )
        result = engine.evaluate({"age": 30})
        assert result.fired_rules == [1]
        assert result.actions == ["allow", "audit"]

    def test_multi_action_survives_the_orm_mapper(self):
        """The ORM stores actions newline-joined; all of them must be written."""
        from fluxrules import Rule
        from fluxrules.persistence.mappers import domain_rule_to_orm

        rule = Rule(
            name="r",
            condition_dsl=_leaf(),
            actions=("escalate", "notify"),
            persist=False,
        )
        orm = domain_rule_to_orm(rule)
        assert orm.action == "escalate\nnotify"


class TestRuntimeRuleRemoval:
    """``RuntimeRule`` is gone, but not silently."""

    def test_old_name_still_resolves(self):
        """Downstream code must not break outright for one release."""
        from fluxrules import Rule

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import fluxrules.engine.infrastructure as infra

            old_name = infra.Rule

        assert old_name is Rule

    def test_runtime_rule_now_warns(self):
        import fluxrules.engine.infrastructure as infra

        with pytest.warns(DeprecationWarning, match=_DEPRECATION_MATCH):
            infra.RuntimeRule(id=1, name="x", condition_dsl=_leaf())

    def test_runtime_rule_constructs_a_canonical_rule(self):
        from fluxrules import Rule

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import fluxrules.engine.infrastructure as infra

            rule = infra.RuntimeRule(id=1, name="x", condition_dsl=_leaf())

        assert isinstance(rule, Rule)

    def test_runtime_rule_never_persists(self):
        """The migration hazard: ``Rule`` persists by default, the old one did not.

        Without this, every migrated call site - including benchmark setup -
        would start writing to a database.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import fluxrules.engine.infrastructure as infra

            rule = infra.RuntimeRule(id=1, name="x", condition_dsl=_leaf())

        assert rule.persist is False

    def test_runtime_rule_accepts_positional_arguments(self):
        """The old dataclass allowed them; the shim must too."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import fluxrules.engine.infrastructure as infra

            rule = infra.RuntimeRule(1, "x", _leaf(), "go")

        assert rule.id == 1
        assert rule.name == "x"
        assert rule.action == "go"

    def test_deprecation_message_names_the_replacement(self):
        """A warning that does not say what to do instead is close to useless."""
        import fluxrules.engine.infrastructure as infra

        with pytest.warns(DeprecationWarning) as record:
            infra.RuntimeRule(id=1, name="x", condition_dsl=_leaf())

        assert "Rule" in str(record[0].message)

    def test_old_name_warns_via_engine_package(self):
        """``fluxrules.engine`` re-exported the same class; same treatment."""
        import fluxrules.engine as engine

        with pytest.warns(DeprecationWarning, match=_DEPRECATION_MATCH):
            engine.Rule

    def test_unknown_attribute_still_raises_attribute_error(self):
        """The module __getattr__ must not swallow genuine typos."""
        import fluxrules.engine as engine
        import fluxrules.engine.infrastructure as infra

        for module in (infra, engine):
            with pytest.raises(AttributeError):
                module.NoSuchAttribute


class TestCanonicalRuleBehaviour:
    """Removing ``RuntimeRule`` must not have changed engine behaviour."""

    def test_construction_requires_no_database(self):
        from fluxrules import Rule

        rule = Rule(id=1, name="x", condition_dsl=_leaf(), persist=False)

        assert rule.domain == "default"
        assert rule.tags == frozenset()

    def test_engines_accept_the_canonical_rule(self):
        from fluxrules import PhreakEngine, Rule

        engine = PhreakEngine()
        engine.load_rules(
            [
                Rule(
                    id=1,
                    name="adult",
                    condition_dsl=_leaf("age", ">=", 18),
                    action="allow",
                    persist=False,
                )
            ]
        )

        assert engine.evaluate({"age": 30}).fired_rules == [1]

    def test_engines_accept_plain_dicts(self):
        from fluxrules import PhreakEngine

        engine = PhreakEngine()
        engine.load_rules(
            [
                {
                    "id": 1,
                    "name": "adult",
                    "condition_dsl": _leaf("age", ">=", 18),
                    "action": "allow",
                }
            ]
        )

        assert engine.evaluate({"age": 30}).fired_rules == [1]
