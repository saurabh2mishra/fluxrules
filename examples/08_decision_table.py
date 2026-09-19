"""Batch 2 example: CSV decision table over shared use case."""

import csv
import io

from fluxrules.domain import Rule
from fluxrules.engine.phreak import PhreakEngine

from shared_use_case import SHARED_FACTS, USE_CASE_NAME, complex_risk_condition


def main() -> None:
    print("=" * 80)
    print("08_decision_table.py")
    print(f"Use case: {USE_CASE_NAME}")
    print("=" * 80)

    csv_data = """name,domain,action,priority
high_risk_cross_border,fraud_detection,manual_review,100
"""

    rules = []
    reader = csv.DictReader(io.StringIO(csv_data))
    for row in reader:
        rule = Rule(
            name=row["name"],
            domain=row["domain"],
            action=row["action"],
            priority=int(row["priority"]),
            condition_dsl=complex_risk_condition(),
        )
        rules.append(rule)

    engine = PhreakEngine()
    engine.load_rules(rules)

    print(f"Loaded {len(rules)} rule(s) from CSV. Evaluating facts...\n")

    for fact in SHARED_FACTS:
        result = engine.evaluate(fact)
        print(
            f"fact={fact['fact_id']} matched={result.fired_rules} actions={result.actions}"
        )


if __name__ == "__main__":
    main()
