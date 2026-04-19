from __future__ import annotations

from fluxrules.domain.models import Ruleset
from fluxrules.domain.predicates import OPERATORS


class ValidationService:
    def validate_ruleset(self, ruleset: Ruleset) -> list[str]:
        issues: list[str] = []
        if not ruleset.rules:
            issues.append("Ruleset is empty")

        ids = [rule.id for rule in ruleset.rules]
        if len(ids) != len(set(ids)):
            issues.append("Ruleset has duplicate rule ids")

        for rule in ruleset.rules:
            if not rule.conditions:
                issues.append(f"Rule '{rule.id}' has no conditions")
            for condition in rule.conditions:
                if condition.operator not in OPERATORS:
                    issues.append(
                        f"Rule '{rule.id}' uses unsupported operator '{condition.operator}'"
                    )

        return issues
