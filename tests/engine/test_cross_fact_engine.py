"""Tests for the cross-fact beta/join engine (PHREAK P3 Track B, B-α + B-β + B-γ + B-δ).

Validates ``.research/PHREAK_P3_PLAN_CROSS_FACT_NETWORK.md``:

- **B-α** fact lifecycle + truth maintenance: insert/update/retract return the
  activation **delta**; a retract *un-fires* dependent activations.
- **B-β** indexed equality joins + token propagation: multi-pattern joins match
  tuples of facts; equality joins probe the hash index.
- **B-γ** collection aggregates (``count``/``sum``/``avg``/``min``/``max``/
  ``collect`` with ``having``) and working-memory quantifiers (``exists`` /
  ``not``), with incremental truth maintenance.
- **B-δ** temporal windows (Allen-style ``within``/``after``/``before``), an
  event clock, and window expiration (stale facts auto-retract, bounding memory).
"""

from __future__ import annotations

import pytest

from fluxrules.engine import get_cross_fact_engine
from fluxrules.engine.cross_fact import (
    Accumulate,
    AlphaConstraint,
    CrossFactEngine,
    CrossFactRule,
    Exists,
    JoinConstraint,
    Pattern,
    TemporalConstraint,
)
from fluxrules.engine.cross_fact.working_memory import CrossFactWorkingMemory


def big_order_gold_rule() -> CrossFactRule:
    """Order(amount > 1000) joined to Customer(tier == gold) on customer_id."""
    return CrossFactRule(
        id=1,
        name="big-order-gold-customer",
        patterns=[
            Pattern("o", "Order", constraints=[("amount", ">", 1000)]),
            Pattern(
                "c",
                "Customer",
                constraints=[("tier", "==", "gold")],
                joins=[("id", "==", "o", "customer_id")],
            ),
        ],
    )


@pytest.fixture
def engine() -> CrossFactEngine:
    e = CrossFactEngine()
    e.load_rules([big_order_gold_rule()])
    return e


# --- B-β: join matching --------------------------------------------------------


class TestJoinMatching:
    def test_two_fact_join_fires(self, engine):
        engine.insert("Customer", {"id": 7, "tier": "gold"})
        delta = engine.insert("Order", {"customer_id": 7, "amount": 5000})
        assert len(delta.added) == 1
        act = delta.added[0]
        assert act.rule_id == 1
        assert act.bindings["o"]["amount"] == 5000
        assert act.bindings["c"]["tier"] == "gold"

    def test_no_fire_when_join_key_mismatches(self, engine):
        engine.insert("Customer", {"id": 7, "tier": "gold"})
        delta = engine.insert("Order", {"customer_id": 99, "amount": 5000})
        assert delta.added == []

    def test_no_fire_when_alpha_fails(self, engine):
        engine.insert("Customer", {"id": 7, "tier": "gold"})
        delta = engine.insert("Order", {"customer_id": 7, "amount": 10})
        assert delta.added == []  # amount not > 1000

    def test_no_fire_when_other_alpha_fails(self, engine):
        engine.insert("Customer", {"id": 7, "tier": "silver"})
        delta = engine.insert("Order", {"customer_id": 7, "amount": 5000})
        assert delta.added == []  # tier not gold

    def test_order_independent_of_insertion(self):
        # Inserting the Order first (before its Customer) must still fire once
        # the Customer arrives.
        e = CrossFactEngine()
        e.load_rules([big_order_gold_rule()])
        assert e.insert("Order", {"customer_id": 7, "amount": 5000}).added == []
        delta = e.insert("Customer", {"id": 7, "tier": "gold"})
        assert len(delta.added) == 1

    def test_fan_out_one_customer_many_orders(self, engine):
        engine.insert("Customer", {"id": 7, "tier": "gold"})
        engine.insert("Order", {"customer_id": 7, "amount": 2000})
        engine.insert("Order", {"customer_id": 7, "amount": 3000})
        assert len(engine.activations()) == 2

    def test_deterministic_activation_order(self, engine):
        engine.insert("Customer", {"id": 7, "tier": "gold"})
        engine.insert("Customer", {"id": 8, "tier": "gold"})
        engine.insert("Order", {"customer_id": 8, "amount": 2000})
        engine.insert("Order", {"customer_id": 7, "amount": 3000})
        acts = engine.activations()
        # Sorted by (rule_id, facts) - reproducible regardless of dict order.
        assert acts == sorted(acts, key=lambda a: (a.rule_id, a.facts))


# --- B-α: truth maintenance ----------------------------------------------------


class TestTruthMaintenance:
    def test_retract_unfires_activation(self, engine):
        cust = engine.insert("Customer", {"id": 7, "tier": "gold"})
        assert cust.added == []  # customer alone fires nothing
        engine.insert("Order", {"customer_id": 7, "amount": 5000})
        # Sanity: one activation exists.
        assert len(engine.activations()) == 1
        delta = engine.retract(cust.handle.id)
        assert len(delta.removed) == 1
        assert engine.activations() == []

    def test_retract_via_engine_inserts(self):
        e = CrossFactEngine()
        e.load_rules([big_order_gold_rule()])
        e.insert("Customer", {"id": 1, "tier": "gold"})
        order_delta = e.insert("Order", {"customer_id": 1, "amount": 2000})
        assert len(order_delta.added) == 1
        removed = e.retract(order_delta.handle.id)
        assert len(removed.removed) == 1
        assert e.get_stats()["active_activations"] == 0

    def test_delta_exposes_affected_handle(self, engine):
        delta = engine.insert("Customer", {"id": 7, "tier": "gold"})
        assert delta.handle is not None
        assert delta.handle.fact_type == "Customer"
        assert delta.handle.fields["id"] == 7

    def test_retract_unknown_handle_has_no_handle(self, engine):
        delta = engine.retract(123456)
        assert delta.handle is None
        assert not delta

    def test_update_breaking_join_removes_activation(self):
        e = CrossFactEngine()
        e.load_rules([big_order_gold_rule()])
        cust = e.insert("Customer", {"id": 7, "tier": "gold"})
        assert cust.added == []  # customer alone fires nothing
        e.insert("Order", {"customer_id": 7, "amount": 5000})
        assert len(e.activations()) == 1
        # Downgrade the customer's tier -> activation must disappear.
        delta = e.update(cust.handle.id, {"id": 7, "tier": "silver"})
        assert len(delta.removed) == 1
        assert e.activations() == []

    def test_update_repairing_join_adds_activation(self):
        e = CrossFactEngine()
        e.load_rules([big_order_gold_rule()])
        cust = e.insert("Customer", {"id": 7, "tier": "silver"})
        assert cust.added == []
        e.insert("Order", {"customer_id": 7, "amount": 5000})
        assert e.activations() == []  # silver, no match yet
        delta = e.update(cust.handle.id, {"id": 7, "tier": "gold"})
        assert len(delta.added) == 1

    def test_retract_missing_handle_is_noop(self, engine):
        delta = engine.retract(99999)
        assert not delta

    def test_clear_drops_all_activations(self, engine):
        engine.insert("Customer", {"id": 7, "tier": "gold"})
        engine.insert("Order", {"customer_id": 7, "amount": 5000})
        assert engine.activations()
        engine.clear()
        assert engine.activations() == []
        assert len(engine.wm) == 0


# --- working memory unit tests -------------------------------------------------


class TestCrossFactWorkingMemory:
    def test_insert_assigns_stable_increasing_ids(self):
        wm = CrossFactWorkingMemory()
        a = wm.insert("T", {"x": 1})
        b = wm.insert("T", {"x": 2})
        assert a.id != b.id
        assert wm.get(a.id) is a

    def test_by_type_groups_facts(self):
        wm = CrossFactWorkingMemory()
        wm.insert("Order", {"x": 1})
        wm.insert("Customer", {"x": 2})
        assert len(wm.by_type("Order")) == 1
        assert len(wm.by_type("Customer")) == 1
        assert wm.by_type("Missing") == []

    def test_equality_index_returns_matches(self):
        wm = CrossFactWorkingMemory()
        wm.insert("Customer", {"id": 1})
        wm.insert("Customer", {"id": 1})
        wm.insert("Customer", {"id": 2})
        assert len(wm.by_equality("Customer", "id", 1)) == 2
        assert len(wm.by_equality("Customer", "id", 2)) == 1
        assert wm.by_equality("Customer", "id", 3) == []

    def test_index_maintained_on_retract(self):
        wm = CrossFactWorkingMemory()
        h = wm.insert("Customer", {"id": 1})
        assert len(wm.by_equality("Customer", "id", 1)) == 1  # build index
        wm.retract(h.id)
        assert wm.by_equality("Customer", "id", 1) == []

    def test_index_maintained_on_update(self):
        wm = CrossFactWorkingMemory()
        h = wm.insert("Customer", {"id": 1})
        assert len(wm.by_equality("Customer", "id", 1)) == 1  # build index
        wm.update(h.id, {"id": 2})
        assert wm.by_equality("Customer", "id", 1) == []
        assert len(wm.by_equality("Customer", "id", 2)) == 1


# --- model + factory -----------------------------------------------------------


class TestModelsAndFactory:
    def test_tuple_constraints_are_coerced(self):
        pat = Pattern("o", "Order", constraints=[("amount", "gt", 100)])
        assert isinstance(pat.constraints[0], AlphaConstraint)
        assert pat.constraints[0].op == ">"  # alias normalized

    def test_tuple_joins_are_coerced(self):
        pat = Pattern("c", "Customer", joins=[("id", "eq", "o", "customer_id")])
        assert isinstance(pat.joins[0], JoinConstraint)
        assert pat.joins[0].op == "=="
        assert pat.joins[0].is_equality

    def test_factory_returns_beta_engine(self):
        e = get_cross_fact_engine()
        assert isinstance(e, CrossFactEngine)

    def test_beta_engine_not_in_single_fact_registry(self):
        from fluxrules.engine import get_available_engines

        assert "BETA" not in get_available_engines()


# --- three-way join (token propagation across >2 patterns) ---------------------


class TestThreeWayJoin:
    def _rule(self) -> CrossFactRule:
        return CrossFactRule(
            id=2,
            name="order-customer-account",
            patterns=[
                Pattern("o", "Order", constraints=[("amount", ">", 100)]),
                Pattern(
                    "c",
                    "Customer",
                    joins=[("id", "==", "o", "customer_id")],
                ),
                Pattern(
                    "a",
                    "Account",
                    constraints=[("status", "==", "active")],
                    joins=[("customer_id", "==", "c", "id")],
                ),
            ],
        )

    def test_three_way_join_fires(self):
        e = CrossFactEngine()
        e.load_rules([self._rule()])
        e.insert("Customer", {"id": 7, "customer_id": 7})
        e.insert("Account", {"customer_id": 7, "status": "active"})
        delta = e.insert("Order", {"customer_id": 7, "amount": 500})
        assert len(delta.added) == 1
        assert delta.added[0].facts and len(delta.added[0].facts) == 3

    def test_three_way_join_breaks_on_middle_retract(self):
        e = CrossFactEngine()
        e.load_rules([self._rule()])
        cust = e.insert("Customer", {"id": 7, "customer_id": 7})
        e.insert("Account", {"customer_id": 7, "status": "active"})
        e.insert("Order", {"customer_id": 7, "amount": 500})
        assert len(e.activations()) == 1
        delta = e.retract(cust.handle.id)
        assert len(delta.removed) == 1
        assert e.activations() == []


# --- B-γ: collection aggregates ------------------------------------------------


def sum_orders_rule(threshold: int = 10000) -> CrossFactRule:
    """Customer with SUM(their orders' amount) >= threshold."""
    return CrossFactRule(
        id=10,
        name="high-value-customer",
        patterns=[
            Pattern("c", "Customer"),
            Accumulate(
                var="total",
                fact_type="Order",
                function="sum",
                field="amount",
                joins=[("customer_id", "==", "c", "id")],
                having=(">=", threshold),
            ),
        ],
    )


class TestAccumulate:
    def test_sum_having_fires_when_threshold_met(self):
        e = CrossFactEngine()
        e.load_rules([sum_orders_rule(10000)])
        e.insert("Customer", {"id": 7})
        e.insert("Order", {"customer_id": 7, "amount": 6000})
        assert e.activations() == []  # 6000 < 10000
        delta = e.insert("Order", {"customer_id": 7, "amount": 5000})
        assert len(delta.added) == 1
        assert delta.added[0].aggregates["total"] == 11000

    def test_retract_drops_below_threshold_and_unfires(self):
        e = CrossFactEngine()
        e.load_rules([sum_orders_rule(10000)])
        e.insert("Customer", {"id": 7})
        e.insert("Order", {"customer_id": 7, "amount": 6000})
        o2 = e.insert("Order", {"customer_id": 7, "amount": 5000})
        assert len(e.activations()) == 1
        delta = e.retract(o2.handle.id)
        assert len(delta.removed) == 1  # 6000 < 10000 -> un-fires
        assert e.activations() == []

    def test_count_needs_no_field(self):
        rule = CrossFactRule(
            id=11,
            name="customer-with-3-orders",
            patterns=[
                Pattern("c", "Customer"),
                Accumulate(
                    var="n",
                    fact_type="Order",
                    function="count",
                    joins=[("customer_id", "==", "c", "id")],
                    having=(">=", 3),
                ),
            ],
        )
        e = CrossFactEngine()
        e.load_rules([rule])
        e.insert("Customer", {"id": 1})
        e.insert("Order", {"customer_id": 1})
        e.insert("Order", {"customer_id": 1})
        assert e.activations() == []
        delta = e.insert("Order", {"customer_id": 1})
        assert len(delta.added) == 1
        assert delta.added[0].aggregates["n"] == 3

    def test_avg_min_max_collect(self):
        for fn, expected in [
            ("avg", 200.0),
            ("min", 100),
            ("max", 300),
            ("collect", [100, 300, 200]),
        ]:
            rule = CrossFactRule(
                id=12,
                name=f"agg-{fn}",
                patterns=[
                    Pattern("c", "Customer"),
                    Accumulate(
                        var="v",
                        fact_type="Order",
                        function=fn,
                        field="amount",
                        joins=[("customer_id", "==", "c", "id")],
                    ),
                ],
            )
            e = CrossFactEngine()
            e.load_rules([rule])
            e.insert("Customer", {"id": 1})
            e.insert("Order", {"customer_id": 1, "amount": 100})
            e.insert("Order", {"customer_id": 1, "amount": 300})
            e.insert("Order", {"customer_id": 1, "amount": 200})
            acts = e.activations()
            assert len(acts) == 1, fn
            value = acts[0].aggregates["v"]
            if fn == "collect":
                assert sorted(value) == sorted(expected), fn
            else:
                assert value == expected, fn

    def test_empty_collection_aggregates(self):
        # No orders: count=0, sum=0, avg/min/max=None. With no `having`, a
        # projection still fires once for the bound customer.
        rule = CrossFactRule(
            id=13,
            name="agg-empty",
            patterns=[
                Pattern("c", "Customer"),
                Accumulate(
                    "s",
                    "Order",
                    "sum",
                    field="amount",
                    joins=[("customer_id", "==", "c", "id")],
                ),
            ],
        )
        e = CrossFactEngine()
        e.load_rules([rule])
        delta = e.insert("Customer", {"id": 99})
        assert len(delta.added) == 1
        assert delta.added[0].aggregates["s"] == 0

    def test_accumulate_is_scoped_by_join(self):
        # Orders of a *different* customer must not contribute to the sum.
        e = CrossFactEngine()
        e.load_rules([sum_orders_rule(10000)])
        e.insert("Customer", {"id": 7})
        e.insert("Order", {"customer_id": 7, "amount": 6000})
        e.insert("Order", {"customer_id": 999, "amount": 9000})  # other customer
        assert e.activations() == []  # only 6000 counts for customer 7

    def test_unknown_function_rejected(self):
        with pytest.raises(ValueError):
            Accumulate("v", "Order", "median", field="amount")

    def test_non_count_requires_field(self):
        with pytest.raises(ValueError):
            Accumulate("v", "Order", "sum")


# --- B-γ: working-memory quantifiers (exists / not) ----------------------------


def order_without_shipment_rule() -> CrossFactRule:
    """An Order that has NO matching Shipment (a 'not' quantifier)."""
    return CrossFactRule(
        id=20,
        name="unshipped-order",
        patterns=[
            Pattern("o", "Order", constraints=[("status", "==", "paid")]),
            Exists(
                fact_type="Shipment",
                joins=[("order_id", "==", "o", "id")],
                negated=True,
            ),
        ],
    )


class TestQuantifiers:
    def test_not_fires_when_no_matching_fact(self):
        e = CrossFactEngine()
        e.load_rules([order_without_shipment_rule()])
        delta = e.insert("Order", {"id": 1, "status": "paid"})
        assert len(delta.added) == 1  # no shipment yet

    def test_not_unfires_when_matching_fact_appears(self):
        e = CrossFactEngine()
        e.load_rules([order_without_shipment_rule()])
        e.insert("Order", {"id": 1, "status": "paid"})
        assert len(e.activations()) == 1
        delta = e.insert("Shipment", {"order_id": 1})
        assert len(delta.removed) == 1  # now shipped -> 'not' fails
        assert e.activations() == []

    def test_not_refires_when_matching_fact_retracted(self):
        e = CrossFactEngine()
        e.load_rules([order_without_shipment_rule()])
        e.insert("Order", {"id": 1, "status": "paid"})
        ship = e.insert("Shipment", {"order_id": 1})
        assert e.activations() == []
        delta = e.retract(ship.handle.id)
        assert len(delta.added) == 1  # shipment gone -> unshipped again

    def test_exists_fires_only_with_matching_fact(self):
        rule = CrossFactRule(
            id=21,
            name="order-with-flag",
            patterns=[
                Pattern("o", "Order"),
                Exists(
                    fact_type="Flag",
                    constraints=[("kind", "==", "fraud")],
                    joins=[("order_id", "==", "o", "id")],
                ),
            ],
        )
        e = CrossFactEngine()
        e.load_rules([rule])
        e.insert("Order", {"id": 1})
        assert e.activations() == []  # no flag
        delta = e.insert("Flag", {"order_id": 1, "kind": "fraud"})
        assert len(delta.added) == 1

    def test_quantifier_binds_no_fact(self):
        # The activation's fact tuple contains only the bound Pattern (the Order),
        # not the existence-checked Shipment.
        e = CrossFactEngine()
        e.load_rules([order_without_shipment_rule()])
        delta = e.insert("Order", {"id": 1, "status": "paid"})
        assert len(delta.added[0].facts) == 1


class TestModelCoercionGamma:
    def test_having_operator_alias_normalized(self):
        acc = Accumulate("v", "Order", "sum", field="amount", having=("gte", 10))
        assert acc.having == (">=", 10)

    def test_exists_default_not_negated(self):
        q = Exists(fact_type="Shipment")
        assert q.negated is False


# --- B-δ: temporal windows -----------------------------------------------------


def rapid_txn_rule(window: float = 300, relation: str = "after") -> CrossFactRule:
    """Two transactions on the same card, the second ``relation`` the first.

    With ``relation="after"`` the pattern ``b`` must occur *after* ``a`` within
    ``window`` - a directional window that matches exactly one ordering of any
    surviving pair (the wrong direction is rejected by the temporal filter, not
    by expiration).
    """
    return CrossFactRule(
        id=30,
        name="rapid-repeat-transaction",
        patterns=[
            Pattern("a", "Txn"),
            Pattern(
                "b",
                "Txn",
                joins=[("card", "==", "a", "card")],
                temporal=[("a", relation, window)],
            ),
        ],
    )


def login_then_charge_rule(window: float = 300) -> CrossFactRule:
    """A Charge ``within`` ``window`` of the same user's Login (two fact types)."""
    return CrossFactRule(
        id=31,
        name="charge-near-login",
        patterns=[
            Pattern("l", "Login"),
            Pattern(
                "c",
                "Charge",
                joins=[("user", "==", "l", "user")],
                temporal=[("l", "within", window)],
            ),
        ],
    )


class TestTemporalWindows:
    def test_after_matches_within_window(self):
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule(window=300, relation="after")])
        e.insert("Txn", {"card": "X", "ts": 100})
        delta = e.insert("Txn", {"card": "X", "ts": 200})
        # b@200 is 100s after a@100 (<= 300): exactly one ordering matches.
        assert len(delta.added) == 1
        act = delta.added[0]
        assert act.bindings["a"]["ts"] == 100
        assert act.bindings["b"]["ts"] == 200

    def test_after_is_directional_one_activation_per_pair(self):
        # Both facts survive (well inside the expiration horizon), so the single
        # activation proves the *temporal filter* rejected the reverse ordering -
        # not expiration.
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule(window=300, relation="after")])
        e.insert("Txn", {"card": "X", "ts": 100})
        e.insert("Txn", {"card": "X", "ts": 200})
        assert len(e.activations()) == 1
        assert len(e.wm) == 2  # neither fact expired

    def test_before_is_directional(self):
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule(window=300, relation="before")])
        e.insert("Txn", {"card": "X", "ts": 200})
        e.insert("Txn", {"card": "X", "ts": 100})
        acts = e.activations()
        assert len(acts) == 1
        # b is the *earlier* event (before a).
        assert acts[0].bindings["a"]["ts"] == 200
        assert acts[0].bindings["b"]["ts"] == 100

    def test_within_is_symmetric(self):
        # `within` is order-independent: a same-type pair within the window
        # matches in both orderings (two activations).
        rule = CrossFactRule(
            id=32,
            name="within-pair",
            patterns=[
                Pattern("a", "Event"),
                Pattern(
                    "b",
                    "Event",
                    joins=[("grp", "==", "a", "grp")],
                    temporal=[("a", "within", 300)],
                ),
            ],
        )
        e = CrossFactEngine()
        e.load_rules([rule])
        e.insert("Event", {"grp": "g", "ts": 1000})
        e.insert("Event", {"grp": "g", "ts": 1200})
        assert len(e.activations()) == 2  # (a,b) and (b,a)

    def test_within_boundary_is_inclusive(self):
        # Exactly `window` apart still matches (<=), and the earlier fact is
        # exactly on the expiration horizon, so it survives.
        e = CrossFactEngine()
        e.load_rules([login_then_charge_rule(window=300)])
        e.insert("Login", {"user": "u", "ts": 1000})
        delta = e.insert("Charge", {"user": "u", "ts": 1300})  # 300 apart, clock=1300
        assert len(delta.added) == 1
        assert len(e.wm) == 2  # Login@1000 sits on the horizon (1300-300) and survives

    def test_two_types_match_within_window(self):
        e = CrossFactEngine()
        e.load_rules([login_then_charge_rule(window=300)])
        e.insert("Login", {"user": "u", "ts": 1000})
        delta = e.insert("Charge", {"user": "u", "ts": 1100})
        assert len(delta.added) == 1

    def test_order_independent_out_of_order_arrival(self):
        # The Charge arrives first; the Login arrives later but is still inside
        # the window relative to the clock, so it survives and the pair fires.
        e = CrossFactEngine()
        e.load_rules([login_then_charge_rule(window=300)])
        assert e.insert("Charge", {"user": "u", "ts": 1300}).added == []
        delta = e.insert("Login", {"user": "u", "ts": 1000})  # clock stays 1300
        assert len(delta.added) == 1

    def test_missing_timestamp_does_not_match(self):
        e = CrossFactEngine()
        e.load_rules([login_then_charge_rule(window=300)])
        e.insert("Login", {"user": "u", "ts": 1000})
        # Charge has no `ts`: it cannot be placed on the timeline -> no match.
        assert e.insert("Charge", {"user": "u"}).added == []

    def test_non_numeric_timestamp_does_not_match(self):
        e = CrossFactEngine()
        e.load_rules([login_then_charge_rule(window=300)])
        e.insert("Login", {"user": "u", "ts": 1000})
        assert e.insert("Charge", {"user": "u", "ts": "noon"}).added == []

    def test_bool_is_not_a_timestamp(self):
        # bool is an int subclass; it must not be treated as event-time 1/0.
        e = CrossFactEngine()
        e.load_rules([login_then_charge_rule(window=300)])
        e.insert("Login", {"user": "u", "ts": 1000})
        assert e.insert("Charge", {"user": "u", "ts": True}).added == []


class TestTemporalExpiration:
    def test_stale_fact_is_auto_retracted(self):
        # A new event far in the future advances the clock past the window,
        # expiring the older facts: memory is bounded.
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule(window=300, relation="after")])
        e.insert("Txn", {"card": "X", "ts": 100})
        e.insert("Txn", {"card": "X", "ts": 200})
        assert len(e.wm) == 2
        e.insert("Txn", {"card": "Y", "ts": 1000})  # clock=1000, horizon=700
        # @100 and @200 are < 700 -> expired; only @1000 remains.
        assert len(e.wm) == 1
        assert e.wm.by_type("Txn")[0].fields["ts"] == 1000

    def test_expiration_unfires_dependent_activation(self):
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule(window=300, relation="after")])
        e.insert("Txn", {"card": "X", "ts": 100})
        e.insert("Txn", {"card": "X", "ts": 200})
        assert len(e.activations()) == 1
        delta = e.insert("Txn", {"card": "Y", "ts": 1000})
        # The (a@100, b@200) match's facts are gone -> it un-fires in this delta.
        assert len(delta.removed) == 1
        assert e.activations() == []

    def test_expiration_applies_to_referenced_type(self):
        # The window bounds *both* sides: the upstream Login type expires too,
        # not just the Charge type that declared the constraint.
        e = CrossFactEngine()
        e.load_rules([login_then_charge_rule(window=300)])
        e.insert("Login", {"user": "u", "ts": 0})
        e.insert("Charge", {"user": "u", "ts": 10})
        assert len(e.activations()) == 1
        e.insert("Charge", {"user": "u", "ts": 1000})  # clock=1000, horizon=700
        # Login@0 and Charge@10 both expire; only Charge@1000 survives.
        assert e.wm.by_type("Login") == []
        assert len(e.wm) == 1

    def test_window_uses_widest_constraint_for_expiration(self):
        # Two windows on the same type: expiration must use the *widest* so a
        # fact still needed by the longer window is not dropped early.
        rule = CrossFactRule(
            id=33,
            name="two-windows",
            patterns=[
                Pattern("a", "E"),
                Pattern(
                    "b",
                    "E",
                    joins=[("g", "==", "a", "g")],
                    temporal=[("a", "after", 100)],
                ),
                Pattern(
                    "c",
                    "E",
                    joins=[("g", "==", "a", "g")],
                    temporal=[("a", "after", 1000)],
                ),
            ],
        )
        e = CrossFactEngine()
        e.load_rules([rule])
        e.insert("E", {"g": "g", "ts": 0})
        e.insert("E", {"g": "g", "ts": 500})  # clock=500, horizon=500-1000=-500
        # @0 is within the *wide* (1000) window's horizon -> must NOT expire.
        assert len(e.wm) == 2

    def test_non_temporal_rules_never_expire(self):
        # Facts carry `ts`, but no rule declares a window -> nothing expires and
        # the clock machinery stays inert (backward compatibility).
        e = CrossFactEngine()
        e.load_rules([big_order_gold_rule()])
        e.insert("Customer", {"id": 7, "tier": "gold", "ts": 0})
        e.insert("Order", {"customer_id": 7, "amount": 5000, "ts": 10_000_000})
        assert len(e.wm) == 2  # nothing expired despite the huge time gap
        assert len(e.activations()) == 1


class TestTemporalClock:
    def test_clock_advances_to_max_timestamp(self):
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule()])
        assert e.clock is None
        e.insert("Txn", {"card": "X", "ts": 100})
        assert e.clock == 100
        e.insert("Txn", {"card": "X", "ts": 250})
        assert e.clock == 250

    def test_clock_does_not_rewind_on_out_of_order_event(self):
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule()])
        e.insert("Txn", {"card": "X", "ts": 500})
        e.insert("Txn", {"card": "X", "ts": 100})  # earlier (out of order)
        assert e.clock == 500  # event-time max, never rewound

    def test_clear_resets_clock(self):
        e = CrossFactEngine()
        e.load_rules([rapid_txn_rule()])
        e.insert("Txn", {"card": "X", "ts": 100})
        e.clear()
        assert e.clock is None

    def test_custom_time_field(self):
        e = CrossFactEngine(time_field="event_ts")
        e.load_rules([login_then_charge_rule(window=300)])
        e.insert("Login", {"user": "u", "event_ts": 1000})
        delta = e.insert("Charge", {"user": "u", "event_ts": 1100})
        assert len(delta.added) == 1
        assert e.clock == 1100


class TestTemporalQuantifierAndAggregate:
    def test_temporal_exists_gates_on_recent_fact(self):
        # Fire for a Login that has a *prior* failed attempt within 60s - an
        # `exists` quantifier carrying a temporal window.
        rule = CrossFactRule(
            id=34,
            name="login-after-recent-failure",
            patterns=[
                Pattern("s", "Success"),
                Exists(
                    fact_type="Failure",
                    joins=[("user", "==", "s", "user")],
                    temporal=[("s", "before", 60)],  # failure before success, <=60s
                ),
            ],
        )
        e = CrossFactEngine()
        e.load_rules([rule])
        e.insert("Failure", {"user": "u", "ts": 1000})
        delta = e.insert("Success", {"user": "u", "ts": 1030})  # 30s later
        assert len(delta.added) == 1

    def test_temporal_accumulate_counts_only_in_window(self):
        # Count a user's clicks that happened within 10s *before* a checkout.
        # A click that survives in working memory but falls on the wrong side of
        # the checkout (after it) must be excluded by the temporal filter - this
        # isolates the window filter from expiration.
        rule = CrossFactRule(
            id=35,
            name="rapid-clicks-before-checkout",
            patterns=[
                Pattern("co", "Checkout"),
                Accumulate(
                    var="n",
                    fact_type="Click",
                    function="count",
                    joins=[("user", "==", "co", "user")],
                    temporal=[("co", "before", 10)],  # click <=10s before checkout
                    having=(">=", 2),
                ),
            ],
        )
        e = CrossFactEngine()
        e.load_rules([rule])
        e.insert("Click", {"user": "u", "ts": 96})
        e.insert("Click", {"user": "u", "ts": 100})
        e.insert("Click", {"user": "u", "ts": 105})  # AFTER the checkout below
        delta = e.insert("Checkout", {"user": "u", "ts": 102})  # clock stays 105
        # All four facts survive (clock=105, horizon=95); clicks@96,100 are before
        # the checkout (within 10s) -> counted; click@105 is after -> filtered.
        assert len(e.wm) == 4
        assert len(delta.added) == 1
        assert delta.added[0].aggregates["n"] == 2


class TestTemporalModel:
    def test_tuple_temporal_is_coerced(self):
        pat = Pattern("b", "Txn", temporal=[("a", "within", 300)])
        assert isinstance(pat.temporal[0], TemporalConstraint)
        assert pat.temporal[0].relation == "within"
        assert pat.temporal[0].window == 300

    def test_temporal_defaults_field_to_none(self):
        tc = TemporalConstraint("a", "after", 60)
        assert tc.this_field is None
        assert tc.other_field is None

    def test_unknown_relation_rejected(self):
        with pytest.raises(ValueError):
            TemporalConstraint("a", "during", 60)

    def test_negative_window_rejected(self):
        with pytest.raises(ValueError):
            TemporalConstraint("a", "within", -1)

    def test_exists_and_accumulate_accept_temporal(self):
        q = Exists(fact_type="F", temporal=[("a", "before", 5)])
        assert isinstance(q.temporal[0], TemporalConstraint)
        acc = Accumulate("v", "F", "count", temporal=[("a", "after", 5)])
        assert isinstance(acc.temporal[0], TemporalConstraint)
