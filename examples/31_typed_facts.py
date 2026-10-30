"""Batch 4 example: typed facts with a Pydantic model.

Payment events usually have a model behind them already. Hand that model to
FluxRules and the engine:

1. evaluates model instances directly (nested models become dotted keys),
2. rejects rules that name a field the model lacks, when the rules load,
3. optionally validates each incoming dict, renaming ``customerCountry`` or
   ``customer-country`` to ``customer_country`` and coercing ``"4200"`` to
   ``4200.0``,
4. decides what happens to a fact that fails validation,
5. runs a fact pipeline first for what a model cannot express (defaults).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from shared_use_case import USE_CASE_NAME

from fluxrules import F, FactValidationError, Rule, UnknownFieldError
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.facts import fields, lenient_aliases
from fluxrules.pipeline import Defaults, FactPipeline


class Account(BaseModel):
    model_config = ConfigDict(alias_generator=lenient_aliases())

    age_days: int
    country: str


class Payment(BaseModel):
    model_config = ConfigDict(alias_generator=lenient_aliases())

    amount: float
    method: str
    channel: str
    account: Account


# fields(Payment) gives checked field references: a typo such as
# p.account.age_day raises UnknownFieldError on the line that writes the rule.
p = fields(Payment)

RULES = [
    Rule(
        id=1,
        name="large_payment_new_account",
        conditions=(p.amount > 2000) & (p.account.age_days < 14),
        action="manual_review",
    ),
    Rule(
        id=2,
        name="prepaid_from_high_risk_country",
        conditions=(p.method == "prepaid_card") & (p.account.country.isin(["NG", "RU"])),
        action="block",
    ),
]


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def main() -> None:
    print("=" * 80)
    print("31_typed_facts.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    section("1. Evaluate a model instance")
    engine = PhreakEngine(fact_schema=Payment)
    engine.load_rules(RULES)
    payment = Payment(
        amount=4200,
        method="prepaid_card",
        channel="web",
        account=Account(age_days=5, country="NG"),
    )
    result = engine.evaluate(payment)
    print(f"matched={result.fired_rules} actions={result.actions}")

    section("2. Rules are checked against the model at load time")
    try:
        engine.load_rules(
            [Rule(id=3, name="typo", conditions=F("account.ageDays") < 14, action="flag")]
        )
    except UnknownFieldError as exc:
        print(f"rejected: {exc}")

    section("3. Normalize raw payloads (key styles and types)")
    normalizing = PhreakEngine(fact_schema=Payment, validate_facts="normalize")
    normalizing.load_rules(RULES)
    raw = {
        "Amount": "4200",
        "method": "card",
        "channel": "api",
        "account": {"ageDays": "5", "country": "US"},
    }
    print(f"raw={raw}")
    print(f"matched={normalizing.evaluate(raw).fired_rules}")

    section("4. Invalid facts: raise or quarantine")
    bad = {
        "amount": "lots",
        "method": "card",
        "channel": "web",
        "account": {"age_days": 5, "country": "US"},
    }
    try:
        normalizing.evaluate(bad)
    except FactValidationError as exc:
        print(f"raised: {exc.errors[0]['loc']} {exc.errors[0]['type']}")

    tolerant = PhreakEngine(
        fact_schema=Payment, validate_facts="normalize", on_invalid="quarantine"
    )
    tolerant.load_rules(RULES)
    print(f"quarantine result: matched={tolerant.evaluate(bad).fired_rules}")
    print(f"quarantined: {[q.facts for q in tolerant.quarantined_facts]}")

    section("5. Fact pipeline first, then validation")
    # The webhook omits "channel"; the pipeline fills it before validation.
    with_defaults = PhreakEngine(
        fact_schema=Payment,
        validate_facts="normalize",
        fact_pipeline=FactPipeline([Defaults({"channel": "webhook"})], name="defaults"),
    )
    with_defaults.load_rules(RULES)
    webhook = {"amount": 3000, "method": "card", "account": {"age_days": 2, "country": "GB"}}
    print(f"matched={with_defaults.evaluate(webhook).fired_rules}")


if __name__ == "__main__":
    main()
