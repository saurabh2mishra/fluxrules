"""Batch 4 example: write your own transform stages.

A custom transform subclasses ``Transform``. It implements ``__call__``, which
takes a fact and returns a new one, and ``metadata``, which names the stage for
inspection and metrics. Custom stages compose with built-in ones using ``>>``,
exactly like any other transform.

``GeoRiskEnricher`` adds a country risk score from a lookup table, and
``VelocityFlag`` derives a boolean the rules can match on directly.
"""

from __future__ import annotations

from typing import Any

from shared_use_case import SHARED_FACTS, USE_CASE_NAME

from fluxrules import F, Rule
from fluxrules.engine.phreak import PhreakEngine
from fluxrules.pipeline import FactPipeline, Transform, TransformMetadata


class GeoRiskEnricher(Transform):
    """Add ``geo_risk`` (0 to 10) from a country lookup table."""

    def __init__(self, risk_by_country: dict[str, int], default: int = 0) -> None:
        self.risk_by_country = risk_by_country
        self.default = default

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="geo_risk_enricher",
            description="Add a 0-10 country risk score",
            required_input_fields=["country"],
            output_fields=["geo_risk"],
        )

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(fact)
        enriched["geo_risk"] = self.risk_by_country.get(fact.get("country"), self.default)
        return enriched


class VelocityFlag(Transform):
    """Add ``high_velocity`` when there were too many payments in the last hour."""

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    @property
    def metadata(self) -> TransformMetadata:
        return TransformMetadata(
            name="velocity_flag",
            required_input_fields=["velocity_1h"],
            output_fields=["high_velocity"],
        )

    def __call__(self, fact: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(fact)
        enriched["high_velocity"] = fact.get("velocity_1h", 0) >= self.threshold
        return enriched


RULE = Rule(
    id=1,
    name="risky_geo_and_velocity",
    conditions=(F("geo_risk") >= 7) & (F("high_velocity") == True),  # noqa: E712
    action="manual_review",
)


def main() -> None:
    print("=" * 80)
    print("29_custom_transforms.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    pipeline = GeoRiskEnricher({"NG": 9, "SN": 7, "GH": 7, "US": 2}) >> VelocityFlag(threshold=5)
    engine = PhreakEngine()
    engine.load_rules([RULE])

    print()
    for raw in SHARED_FACTS:
        fact = pipeline(raw)
        result = engine.evaluate(fact)
        print(
            f"{fact['fact_id']}: country={fact['country']} geo_risk={fact['geo_risk']} "
            f"velocity_1h={fact['velocity_1h']} high_velocity={fact['high_velocity']} "
            f"-> matched={result.fired_rules}"
        )

    described = FactPipeline([GeoRiskEnricher({}), VelocityFlag(5)], name="enrich")
    print()
    for step in described.inspect()["transforms"]:
        print(f"inspect: {step['name']:18} reads={step['required_input']} writes={step['output']}")


if __name__ == "__main__":
    main()
