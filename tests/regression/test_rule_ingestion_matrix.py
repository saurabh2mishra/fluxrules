"""The ingestion contract: a rule fires exactly on the facts it should.

Every authoring path must funnel into the same behaviour. This matrix is the
contract referenced by the fix plan for "persisted rules silently match
nothing" - the failure mode it exists to prevent is *not* an exception but a
confident, plausible, wrong answer:

- a rule that should match firing nothing (conditions lost in translation), and
- a rule whose conditions were lost matching *everything* (vacuous truth).

Both are invisible to a test that only checks "no error was raised", so every
assertion here is behavioural: given these facts, exactly these rules fire.

Axes:
    ingestion  x  DSL shape  x  engine
"""

from __future__ import annotations

import warnings

import pytest

from fluxrules import Rule
from fluxrules.domain.models import Ruleset
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.persistence.mappers import (
    domain_rule_to_orm,
    orm_rule_to_canonical,
)
from fluxrules.services.reference_evaluator import ReferenceEvaluator

# ── DSL shapes, each with the facts that must and must not match ─────────────


def _leaf() -> dict:
    return {"type": "condition", "field": "amount", "op": ">", "value": 100}


def _and() -> dict:
    return {
        "type": "and",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "country", "op": "==", "value": "US"},
        ],
    }


def _group_and() -> dict:
    return {
        "type": "group",
        "op": "AND",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "country", "op": "==", "value": "US"},
        ],
    }


def _or() -> dict:
    return {
        "type": "or",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {"type": "condition", "field": "country", "op": "==", "value": "US"},
        ],
    }


def _nested() -> dict:
    """``amount > 100 AND (country == US OR vip == True)``."""
    return {
        "type": "and",
        "children": [
            {"type": "condition", "field": "amount", "op": ">", "value": 100},
            {
                "type": "or",
                "children": [
                    {
                        "type": "condition",
                        "field": "country",
                        "op": "==",
                        "value": "US",
                    },
                    {"type": "condition", "field": "vip", "op": "==", "value": True},
                ],
            },
        ],
    }


# (id, dsl factory, matching fact sets, non-matching fact sets)
SHAPES = [
    (
        "leaf",
        _leaf,
        [{"amount": 500, "country": "UK"}],
        [{"amount": 50, "country": "US"}],
    ),
    (
        "and",
        _and,
        [{"amount": 500, "country": "US"}],
        [{"amount": 500, "country": "UK"}, {"amount": 50, "country": "US"}],
    ),
    (
        "group_and",
        _group_and,
        [{"amount": 500, "country": "US"}],
        [{"amount": 500, "country": "UK"}, {"amount": 50, "country": "US"}],
    ),
    (
        "or",
        _or,
        [
            {"amount": 500, "country": "UK"},  # left only
            {"amount": 50, "country": "US"},  # right only
            {"amount": 500, "country": "US"},  # both
        ],
        [{"amount": 50, "country": "UK"}],
    ),
    (
        "nested",
        _nested,
        [
            {"amount": 500, "country": "US", "vip": False},
            {"amount": 500, "country": "UK", "vip": True},
        ],
        [
            {"amount": 500, "country": "UK", "vip": False},  # outer AND fails
            {"amount": 50, "country": "US", "vip": True},  # inner OR ok, outer fails
        ],
    ),
]

SHAPE_IDS = [s[0] for s in SHAPES]


# ── Ingestion paths: each returns a canonical Rule ────────────────────────────


def _via_authoring(dsl: dict) -> Rule:
    return Rule(id=7, name="matrix", condition_dsl=dsl, action="flag", persist=False)


def _via_dict(dsl: dict) -> Rule:
    return Rule(id=7, name="matrix", condition_dsl=dsl, action="flag", persist=False)


def _via_yaml(dsl: dict) -> Rule:
    import yaml

    payload = yaml.safe_load(
        yaml.safe_dump({"id": 7, "name": "matrix", "condition_dsl": dsl, "action": "flag"})
    )
    payload["persist"] = False
    return Rule.model_validate_yaml(payload)


def _via_engine_rule(dsl: dict) -> Rule:
    """Round trip through the flat ``EngineRule`` and back."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        engine_rule = _via_authoring(dsl).to_engine_rule()
    return Rule.from_engine_rule(engine_rule, persist=False)


def _via_orm(dsl: dict) -> Rule:
    """The path that used to lose everything: Rule -> ORM row -> Rule."""
    orm = domain_rule_to_orm(_via_authoring(dsl), group="matrix")
    orm.id = 7
    orm.created_at = None
    orm.updated_at = None
    return orm_rule_to_canonical(orm)


INGESTIONS = [
    ("authoring", _via_authoring),
    ("dict", _via_dict),
    ("yaml", _via_yaml),
    ("engine_rule", _via_engine_rule),
    ("orm", _via_orm),
]

INGESTION_IDS = [i[0] for i in INGESTIONS]


# ── Engines, normalised to "which rule ids fired" ─────────────────────────────


def _fire_phreak(rule: Rule, facts: dict) -> list:
    engine = PhreakEngine()
    engine.load_rules([rule])
    return list(engine.evaluate(facts).fired_rules)


def _fire_reference(rule: Rule, facts: dict) -> list:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ruleset = Ruleset(group="matrix", rules=(rule.to_engine_rule(),))
    return list(ReferenceEvaluator().evaluate(ruleset, facts).matched_rule_ids)


ENGINES = [
    ("phreak", _fire_phreak),
    ("reference", _fire_reference),
]

ENGINE_IDS = [e[0] for e in ENGINES]


@pytest.mark.parametrize("engine_name,fire", ENGINES, ids=ENGINE_IDS)
@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
@pytest.mark.parametrize("ingest_name,ingest", INGESTIONS, ids=INGESTION_IDS)
def test_rule_fires_exactly_where_it_should(ingest_name, ingest, shape, engine_name, fire):
    """Every cell of ingestion x shape x engine agrees on the same answer."""
    shape_name, make_dsl, matching, non_matching = shape

    rule = ingest(make_dsl())

    for facts in matching:
        assert fire(rule, facts) == [rule.id], (
            f"{ingest_name}/{shape_name}/{engine_name}: expected a match for "
            f"{facts}, got none - a rule that should fire fired nothing"
        )

    for facts in non_matching:
        assert fire(rule, facts) == [], (
            f"{ingest_name}/{shape_name}/{engine_name}: expected no match for "
            f"{facts}, but the rule fired - matching more than it should"
        )


@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
def test_orm_round_trip_preserves_the_dsl_verbatim(shape):
    """``condition_dsl`` is persisted as-is, not flattened into conditions."""
    _, make_dsl, _, _ = shape
    dsl = make_dsl()

    orm = domain_rule_to_orm(_via_authoring(dsl), group="matrix")
    orm.id = 7
    orm.created_at = None
    orm.updated_at = None

    assert orm.condition_dsl == dsl
    assert orm_rule_to_canonical(orm).condition_dsl == dsl


@pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
def test_engine_rule_round_trip_preserves_dsl(shape):
    """The lossy view carries the DSL alongside, so nothing is destroyed."""
    _, make_dsl, _, _ = shape
    dsl = make_dsl()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        engine_rule = _via_authoring(dsl).to_engine_rule()

    assert engine_rule.condition_dsl == dsl
    assert Rule.from_engine_rule(engine_rule, persist=False).condition_dsl == dsl


class TestLossIsLoud:
    """Whenever the flat view cannot hold the logic, say so."""

    def test_flattening_an_or_warns(self):
        rule = _via_authoring(_or())
        with pytest.warns(Warning, match="cannot be represented"):
            _ = rule.conditions

    def test_flattening_an_and_does_not_warn(self):
        rule = _via_authoring(_and())
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert len(rule.conditions) == 2

    def test_conditions_are_never_silently_dropped(self):
        """The original defect: `and`/`or` nodes yielded an empty tuple."""
        for make_dsl in (_and, _or, _group_and, _nested):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                conditions = _via_authoring(make_dsl()).conditions
            assert conditions, f"{make_dsl.__name__} lost all of its conditions"


class TestEmptinessNeverMatches:
    """A rule with nothing to match on must not match everything."""

    def test_reference_evaluator_declines_a_conditionless_rule(self):
        from fluxrules.domain.models import EngineRule

        ruleset = Ruleset(
            group="matrix",
            rules=(EngineRule(id=1, name="empty", conditions=(), actions=("flag",)),),
        )
        result = ReferenceEvaluator().evaluate(ruleset, {"anything": 0})

        assert result.matched_rule_ids == []
        assert result.actions == []

    def test_empty_group_does_not_match_by_vacuous_truth(self):
        from fluxrules.domain.dsl.evaluator import evaluate_dsl

        assert evaluate_dsl({"type": "and", "children": []}, {"a": 1}) is False
        assert evaluate_dsl({"type": "or", "children": []}, {"a": 1}) is False


class TestEmptyRulesCannotBeCreatedOrStored:
    """A rule that could never fire must not be authorable or persistable.

    The runtime is now correct, but correctness at evaluation time is not
    enough: a rule with no logic that reaches the database becomes permanent,
    silent damage. It loads without error, reports nothing wrong, and never
    fires. These guards exist so that failure happens at the moment the
    information still exists to fix it.
    """

    EMPTY_SHAPES = [
        {"type": "and", "children": []},
        {"type": "or", "children": []},
        {"type": "and", "conditions": []},
        {"type": "group", "op": "AND", "children": []},
        # Empty all the way down: nesting must not disguise emptiness.
        {"type": "and", "children": [{"type": "or", "children": []}]},
    ]

    @pytest.mark.parametrize("dsl", EMPTY_SHAPES)
    def test_authoring_an_empty_rule_is_refused(self, dsl):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="could never fire"):
            Rule(name="empty", condition_dsl=dsl, action="flag", persist=False)

    @pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
    def test_real_rules_are_still_accepted(self, shape):
        """The guard must not reject rules that carry genuine logic."""
        _, make_dsl, _, _ = shape
        assert _via_authoring(make_dsl()).condition_dsl == make_dsl()

    def test_persisting_a_conditionless_rule_is_refused(self):
        """The write boundary is the last point where the loss is preventable."""
        from fluxrules.domain.errors import EmptyRuleLogicError
        from fluxrules.domain.models import EngineRule

        engine_rule = EngineRule(id=1, name="empty", conditions=(), actions=("flag",))
        with pytest.raises(EmptyRuleLogicError, match="could never fire"):
            domain_rule_to_orm(engine_rule, group="matrix")

    def test_the_historical_damage_can_no_longer_be_written(self):
        """Reproduces exactly how `condition_dsl=[]` rows came to exist.

        A valid AND rule was flattened through the lossy `.conditions` view on
        its way to the database, arriving with no logic at all. Both halves are
        now closed: the flattening keeps the DSL, and the write refuses an
        empty one.
        """
        rule = _via_authoring(_and())
        orm = domain_rule_to_orm(rule, group="matrix")

        assert orm.condition_dsl == _and()
        assert orm.condition_dsl != []

    def test_error_names_the_rule_and_suggests_a_fix(self):
        """An error nobody can act on just moves the problem."""
        from fluxrules.domain.errors import EmptyRuleLogicError
        from fluxrules.domain.models import EngineRule

        with pytest.raises(EmptyRuleLogicError) as exc:
            domain_rule_to_orm(
                EngineRule(id=1, name="payment-check", conditions=(), actions=()),
                group="matrix",
            )

        message = str(exc.value)
        assert "payment-check" in message
        assert "always-true" in message


class TestOneStoredShape:
    """``condition_dsl`` is always written as a DSL dict, never a list.

    The column used to accept two shapes - a DSL tree, or a flat list of
    ``{fact, operator, value}`` dicts - depending on which writer produced it.
    Every reader then had to handle both, and the two branches drifted apart:
    that divergence is precisely how the nested-DSL branch came to drop every
    condition. One shape in means readers never have to guess.
    """

    def _engine_rule(self, *conditions):
        from fluxrules.domain.models import EngineRule

        return EngineRule(id=1, name="stored", conditions=tuple(conditions), actions=("flag",))

    def _condition(self, fact="amount", operator="gt", value=100):
        from fluxrules.domain.models import RuleCondition

        return RuleCondition(fact=fact, operator=operator, value=value)

    def test_engine_rule_with_one_condition_stores_a_leaf(self):
        orm = domain_rule_to_orm(self._engine_rule(self._condition()), group="g")

        assert isinstance(orm.condition_dsl, dict)
        assert orm.condition_dsl == {
            "type": "condition",
            "field": "amount",
            "op": "gt",
            "value": 100,
        }

    def test_engine_rule_with_several_conditions_stores_an_and_tree(self):
        orm = domain_rule_to_orm(
            self._engine_rule(
                self._condition(),
                self._condition(fact="country", operator="eq", value="US"),
            ),
            group="g",
        )

        assert isinstance(orm.condition_dsl, dict)
        assert orm.condition_dsl["type"] == "and"
        assert [c["field"] for c in orm.condition_dsl["children"]] == [
            "amount",
            "country",
        ]

    @pytest.mark.parametrize("shape", SHAPES, ids=SHAPE_IDS)
    @pytest.mark.parametrize("ingest_name,ingest", INGESTIONS, ids=INGESTION_IDS)
    def test_no_ingestion_path_stores_a_list(self, ingest_name, ingest, shape):
        """Whichever way a rule is authored, the column shape is the same."""
        _, make_dsl, _, _ = shape
        rule = ingest(make_dsl())
        orm = domain_rule_to_orm(rule, group="g")

        assert isinstance(orm.condition_dsl, dict), (
            f"{ingest_name} stored a {type(orm.condition_dsl).__name__}, "
            "reintroducing the two-shape ambiguity"
        )
        assert "type" in orm.condition_dsl

    def test_legacy_list_rows_are_rejected(self):
        """A list-shaped column is corrupt, not old, and must not load quietly.

        Coercing it into an ``and`` tree would be a guess about intent; loading
        it as empty would match nothing, which looks exactly like a correct
        evaluation. Neither failure is visible, so this raises instead.
        """
        import pytest

        from fluxrules.domain.errors import CorruptStoredRuleError
        from fluxrules.persistence.mappers import normalize_stored_dsl

        legacy = [
            {"fact": "amount", "operator": "gt", "value": 100},
            {"fact": "country", "operator": "eq", "value": "US"},
        ]

        with pytest.raises(CorruptStoredRuleError):
            normalize_stored_dsl(legacy)

    def test_json_string_rows_are_rejected(self):
        """The API path no longer double-encodes, so a str column is corrupt."""
        import json

        import pytest

        from fluxrules.domain.errors import CorruptStoredRuleError
        from fluxrules.persistence.mappers import normalize_stored_dsl

        with pytest.raises(CorruptStoredRuleError):
            normalize_stored_dsl(json.dumps(_leaf()))

    def test_absent_logic_is_not_corruption(self):
        """``None``/``{}`` mean "no logic yet", which is legitimate."""
        from fluxrules.persistence.mappers import normalize_stored_dsl

        empty = {"type": "and", "children": []}
        assert normalize_stored_dsl(None) == empty
        assert normalize_stored_dsl({}) == empty

    def test_round_trip_through_storage_is_stable(self):
        """Storing an already-stored rule must not change its shape again."""
        rule = _via_authoring(_nested())

        first = domain_rule_to_orm(rule, group="g")
        first.id = 7
        first.created_at = None
        first.updated_at = None

        reloaded = orm_rule_to_canonical(first)
        second = domain_rule_to_orm(reloaded, group="g")

        assert second.condition_dsl == first.condition_dsl == _nested()


class TestLossyViewCannotBeRebuilt:
    """An OR must never come back as an AND.

    Flattening ``OR(a, b)`` yields exactly the same two leaves as
    ``AND(a, b)``. Rebuilding a tree from those leaves therefore produced an
    ``and`` node and silently *narrowed* the rule - it now required both
    conditions where it previously accepted either, so it fired strictly less
    often. Nothing raised, the stored row was well-formed, and the rule read
    correctly in every listing; the only symptom was actions that never
    happened.

    The pre-existing warning could not prevent this, because a warning does
    not stop the write.
    """

    def _view(self, dsl: dict):
        from fluxrules.domain.factory import _extract_conditions_from_dsl

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _extract_conditions_from_dsl(dsl)

    def test_or_flattens_to_the_same_leaves_as_and(self):
        """The premise: the leaves alone cannot tell the two trees apart."""
        assert tuple(self._view(_or())) == tuple(self._view(_and()))

    def test_or_view_is_marked_lossy(self):
        assert self._view(_or()).lossy is True

    def test_and_view_is_not_lossy(self):
        assert self._view(_and()).lossy is False

    def test_loss_propagates_out_of_a_nested_subtree(self):
        """An AND containing an OR is no more reconstructible than the OR."""
        and_over_or = {
            "type": "and",
            "children": [
                _or(),
                {"type": "condition", "field": "c", "op": "eq", "value": 3},
            ],
        }
        assert self._view(and_over_or).lossy is True

    def test_rebuilding_from_a_lossy_view_is_refused(self):
        from fluxrules.domain.dsl.evaluator import (
            LossyConditionRebuildError,
            conditions_to_dsl,
        )

        with pytest.raises(LossyConditionRebuildError):
            conditions_to_dsl(self._view(_or()))

    def test_rebuilding_from_a_faithful_view_still_works(self):
        """The guard must not block the legitimate conjunction case."""
        from fluxrules.domain.dsl.evaluator import conditions_to_dsl

        assert conditions_to_dsl(self._view(_and()))["type"] == "and"

    def test_a_plain_tuple_is_still_accepted(self):
        """Callers that build conditions by hand are unaffected."""
        from fluxrules.domain.dsl.evaluator import conditions_to_dsl
        from fluxrules.domain.models import RuleCondition

        conditions = (RuleCondition(fact="amount", operator="gt", value=100),)
        assert conditions_to_dsl(conditions)["type"] == "condition"

    def test_the_view_is_still_an_ordinary_tuple(self):
        """Every existing consumer iterates/len()s this; it must not break."""
        view = self._view(_and())
        assert isinstance(view, tuple)
        assert len(view) == 2
        assert view == tuple(view)


class TestLossyRebuildIsACompatibleChange:
    """The guard must not become a breaking change for ordinary consumers.

    ``ConditionView`` is a ``tuple`` subclass on purpose: making the flat view
    carry provenance must not disturb the many call sites that only iterate it,
    measure it, or compare it. These pin the compatibility promise made in the
    changelog, so a future change to ``ConditionView`` cannot quietly withdraw
    it.
    """

    def _view(self, dsl: dict):
        from fluxrules.domain.factory import _extract_conditions_from_dsl

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _extract_conditions_from_dsl(dsl)

    def test_lossy_view_still_behaves_as_a_plain_tuple(self):
        """Reading a lossy view must stay unaffected - only rebuilding raises."""
        view = self._view(_or())

        assert isinstance(view, tuple)
        assert len(view) == 2
        assert bool(view) is True
        assert view[0] == tuple(view)[0]
        assert view == tuple(view)
        assert list(view) == list(view)

    def test_error_is_catchable_as_the_package_base_error(self):
        """Existing `except FluxRulesError` handlers must keep working."""
        from fluxrules.domain.dsl.evaluator import conditions_to_dsl
        from fluxrules.domain.errors import FluxRulesError, InvalidRuleError

        with pytest.raises(FluxRulesError):
            conditions_to_dsl(self._view(_or()))
        with pytest.raises(InvalidRuleError):
            conditions_to_dsl(self._view(_or()))

    def test_error_carries_a_stable_code(self):
        from fluxrules.domain.dsl.evaluator import (
            LossyConditionRebuildError,
            conditions_to_dsl,
        )

        with pytest.raises(LossyConditionRebuildError) as excinfo:
            conditions_to_dsl(self._view(_or()))
        assert excinfo.value.code == "LOSSY_CONDITION_REBUILD"

    def test_error_message_names_the_remedy(self):
        """A raise that does not say what to do instead is a support ticket."""
        from fluxrules.domain.dsl.evaluator import (
            LossyConditionRebuildError,
            conditions_to_dsl,
        )

        with pytest.raises(LossyConditionRebuildError) as excinfo:
            conditions_to_dsl(self._view(_or()))
        assert "condition_dsl" in str(excinfo.value)

    def test_normal_authoring_never_reaches_the_error(self):
        """The documented escape hatch: authored rules carry their DSL.

        If this fails, the guard has started firing on a working path rather
        than on the corruption it was written to stop.
        """
        rule = _via_authoring(_or())
        engine_rule = rule.to_engine_rule()

        assert engine_rule.condition_dsl == _or()
        assert domain_rule_to_orm(engine_rule, group="g").condition_dsl == _or()
