"""End-to-end integration tests for the FactPipeline framework.

Exercises sources -> pipeline -> loader -> real PhreakEngine, demonstrating
all features working together.
"""

from __future__ import annotations

import json

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import (
    CSVSource,
    Defaults,
    ErrorAction,
    ErrorPolicy,
    FactLoader,
    FactPipeline,
    FieldType,
    Flatten,
    IterableSource,
    JSONSource,
    MetricsHook,
    PipelineMetrics,
    Rename,
    Require,
)


def build_engine() -> PhreakEngine:
    engine = PhreakEngine()
    engine.load_rules(
        [
            Rule(
                name="high_value_new_account",
                condition_dsl={
                    "type": "composite",
                    "logic": "AND",
                    "conditions": [
                        {
                            "type": "condition",
                            "field": "amount",
                            "op": ">",
                            "value": 1000,
                        },
                        {
                            "type": "condition",
                            "field": "account_age_days",
                            "op": "<",
                            "value": 30,
                        },
                    ],
                },
                action="flag_for_review",
                priority=10,
                persist=False,
            ),
            Rule(
                name="high_risk_country",
                condition_dsl={
                    "type": "condition",
                    "field": "country",
                    "op": "in",
                    "value": ["NG", "RU"],
                },
                action="enhanced_due_diligence",
                priority=5,
                persist=False,
            ),
        ]
    )
    return engine


def make_normalize() -> FactPipeline:
    return FactPipeline(
        [
            Flatten(),
            Rename(
                {
                    "user_id": ["user.id", "userId", "user_id"],
                    "amount": ["order.amount", "amount_cents", "amount"],
                    "account_age_days": [
                        "user.profile.account_age_days",
                        "account_age_days",
                    ],
                    "country": ["device.country", "country_code", "country"],
                }
            ),
            FieldType({"amount": float, "account_age_days": int}),
            Defaults({"account_age_days": 0}),
            Require(["user_id", "amount"]),
        ]
    )


class TestEndToEndEngine:
    def test_nested_json_source_fires_rules(self):
        engine = build_engine()
        rest_json = json.dumps(
            [
                {
                    "user": {"id": "u_1", "profile": {"account_age_days": 12}},
                    "order": {"amount": 5000.0},
                    "device": {"country": "NG"},
                }
            ]
        )
        loader = FactLoader(JSONSource(rest_json), make_normalize())
        facts = list(loader)
        assert len(facts) == 1
        result = engine.evaluate(facts[0])
        assert "flag_for_review" in result.actions
        assert "enhanced_due_diligence" in result.actions

    def test_csv_source_cents_conversion(self):
        engine = build_engine()
        csv_pipeline = FactPipeline(
            [
                Flatten(),
                Rename(
                    {
                        "user_id": ["user_id"],
                        "amount": ["amount_cents"],
                        "account_age_days": ["account_age_days"],
                        "country": ["country_code"],
                    }
                ),
                FieldType({"amount": lambda c: float(c) / 100, "account_age_days": int}),
                Defaults({"account_age_days": 0}),
                Require(["user_id", "amount"]),
            ]
        )
        db_csv = "user_id,amount_cents,account_age_days,country_code\nu_3,99900,5,RU\n"
        loader = FactLoader(CSVSource(db_csv), csv_pipeline)
        fact = next(iter(loader))
        assert fact["amount"] == 999.0
        result = engine.evaluate(fact)
        assert "enhanced_due_diligence" in result.actions

    def test_error_policy_routes_bad_records(self):
        engine = build_engine()
        messy = IterableSource(
            [
                {
                    "userId": "ok_1",
                    "amount": 1200,
                    "account_age_days": 3,
                    "country": "NG",
                },
                {"userId": "bad_1", "country": "US"},  # missing amount
            ]
        )
        loader = FactLoader(messy, make_normalize(), on_error="collect")
        good = list(loader)
        assert [f["user_id"] for f in good] == ["ok_1"]
        assert len(loader.dead_letter) == 1
        # The single good record still fires rules.
        assert engine.evaluate(good[0]).actions


class TestIntegration:
    def test_metrics_collected_across_sources(self):
        metrics = PipelineMetrics()
        pipeline = make_normalize()
        pipeline.hooks = [MetricsHook(metrics)]
        loader = FactLoader(
            IterableSource([{"userId": f"u_{i}", "amount": 100 * i} for i in range(1, 4)]),
            pipeline,
        )
        list(loader)
        assert metrics.pipeline_runs == 3
        assert metrics.transform_invocations["Flatten"] == 3

    def test_serialize_then_reload_pipeline(self):
        original = FactPipeline([Flatten(), Rename({"user_id": ["userId"]}), Require(["user_id"])])
        spec = original.to_dict()
        reloaded = FactPipeline.from_dict(spec)
        fact = {"userId": "u_9"}
        assert reloaded(dict(fact)) == original(dict(fact))

    def test_skip_policy_drops_without_dead_letter(self):
        pipeline = make_normalize()
        pipeline.error_policy = ErrorPolicy(default=ErrorAction.SKIP)
        loader = FactLoader(
            IterableSource(
                [
                    {"userId": "good", "amount": 10},
                    {"userId": "bad"},  # missing amount -> skipped by policy
                ]
            ),
            pipeline,
        )
        out = list(loader)
        assert [f["user_id"] for f in out] == ["good"]
        assert loader.dead_letter == []
