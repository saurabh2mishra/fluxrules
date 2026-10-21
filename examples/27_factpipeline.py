"""Batch 4 example: the FactPipeline framework.

A ``FactPipeline`` is an ordered list of transforms that turns a raw input into
a fact the engine can match. This example shows the four parts of the framework:

1. **Transforms**: ``Rename``, ``FieldType``, ``Defaults`` and ``Require``.
2. **Composition**: ``a >> b`` runs ``a`` then ``b``; ``a | b`` tries ``a`` and
   falls back to ``b`` if ``a`` raises.
3. **Observability**: ``MetricsHook`` counts runs and timings, and
   ``inspect()`` describes what each transform reads and writes.
4. **Versioning**: ``PipelineVersion`` fingerprints a pipeline, and
   ``diff_pipelines`` reports what changed between two versions.
"""

from __future__ import annotations

from shared_use_case import USE_CASE_NAME, build_shared_rules

from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import (
    Defaults,
    FactPipeline,
    FieldType,
    MetricsHook,
    PipelineMetrics,
    PipelineVersion,
    Rename,
    Require,
    diff_pipelines,
)

# A partner sends camelCase fields and string numbers.
PARTNER_EVENT = {
    "fact_id": "txn-001",
    "txnAmount": "4200",
    "velocity_1h": 6,
    "chargebackRatio": "0.14",
    "country": "NG",
    "ip_risk_score": 88,
    "device_age_days": 2,
    "account_age_days": 5,
    "email_domain": "newmail.example",
    "payment_method": "prepaid_card",
    "customer_tier": "standard",
    "tags": ["manual_review_candidate"],
}


def main() -> None:
    print("=" * 80)
    print("27_factpipeline.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    # 1. Transforms, 2. composition: clean >> validate
    clean = FactPipeline(
        [
            Rename({"amount": ["txnAmount"], "chargeback_ratio": ["chargebackRatio"]}),
            FieldType({"amount": float, "chargeback_ratio": float}),
            Defaults({"currency": "USD"}),
        ],
        name="clean",
    )
    validate = FactPipeline([Require(["fact_id", "amount", "country"])], name="validate")
    normalize = clean >> validate

    fact = normalize(PARTNER_EVENT)
    print(f"\nnormalized fact: amount={fact['amount']!r} chargeback_ratio={fact['chargeback_ratio']!r}")
    print(f"                 currency={fact['currency']!r} (filled in by Defaults)")

    engine = PhreakEngine()
    engine.load_rules(build_shared_rules())
    print(f"matched={engine.evaluate(fact).fired_rules}")

    # Fallback: a record that fails validation falls back to a safe default.
    strict = FactPipeline([Require(["amount"])], name="strict")
    lenient = FactPipeline([Defaults({"amount": 0.0})], name="lenient")
    resilient = strict | lenient
    print(f"\nfallback on a record with no amount -> {resilient({'fact_id': 'txn-x'})}")

    # 3. Observability
    metrics = PipelineMetrics()
    observed = FactPipeline(
        [Rename({"amount": ["txnAmount"]}), FieldType({"amount": float})],
        name="observed",
        hooks=[MetricsHook(metrics)],
    )
    for _ in range(3):
        observed(PARTNER_EVENT)
    print(f"\nmetrics: runs={metrics.pipeline_runs} errors={metrics.pipeline_errors}")
    print(f"         transform calls={dict(metrics.transform_invocations)}")
    for step in clean.inspect()["transforms"]:
        print(f"inspect: {step['name']:10} reads={step['required_input']} writes={step['output']}")

    # 4. Versioning: an added output field is compatible; inserting, removing or
    # reordering a transform is breaking.
    def clean_with(*extra, defaults=None):
        return FactPipeline(
            [
                Rename({"amount": ["txnAmount"], "chargeback_ratio": ["chargebackRatio"]}),
                FieldType({"amount": float, "chargeback_ratio": float}),
                Defaults(defaults or {"currency": "USD"}),
                *extra,
            ],
            name="clean",
        )

    v1 = PipelineVersion.from_pipeline(clean_with(), version="1.0.0")
    v1_1 = PipelineVersion.from_pipeline(
        clean_with(defaults={"currency": "USD", "channel": "web"}), version="1.1.0"
    )
    v2 = PipelineVersion.from_pipeline(clean_with(Require(["amount"])), version="2.0.0")
    print()
    for new, what in ((v1_1, "adds a 'channel' default"), (v2, "inserts a Require stage")):
        diff = diff_pipelines(v1, new)
        print(
            f"1.0.0 -> {new.version} ({what}): {diff.change_type.value}, "
            f"added outputs={sorted(diff.added_outputs)}"
        )

if __name__ == "__main__":
    main()
