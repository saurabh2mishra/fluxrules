"""A comparison that could not be made, as reported in an evaluation result.

``"abc" > 5``, ``None > 5``, ``float("nan") > 5``, a ``date`` ordered against a
``datetime``, ``contains`` on a number and an invalid regex all have no
answer. The condition is no match, and the evaluation lists each case in
``EvaluationResult.comparison_issues`` as a :class:`ComparisonIssue`.
``EngineConfig.uncomparable`` chooses whether it also warns, makes ``NOT``
over it unknown, or raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["ComparisonIssue", "type_label"]


def type_label(value: Any) -> str:
    """The type name shown for *value*: ``"int"``, ``"str"``, ``"None"``."""
    return "None" if value is None else type(value).__name__


@dataclass(frozen=True, slots=True)
class ComparisonIssue:
    """One kind of comparison that could not be made.

    Issues are identified by field, operator, both types and the reason, so
    the same comparison repeated over many rules is listed once.

    Attributes:
        field: The fact field the condition reads.
        operator: The condition's operator, such as ``">"`` or ``"regex"``.
        fact_type: The type of the fact's value, such as ``"str"``.
        rule_type: The type of the rule's value, such as ``"int"``.
        reason: Why the comparison could not be made.
    """

    field: str
    operator: str
    fact_type: str
    rule_type: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        """The issue as a JSON-ready dict, as the CLI and HTTP API return it."""
        return {
            "field": self.field,
            "operator": self.operator,
            "fact_type": self.fact_type,
            "rule_type": self.rule_type,
            "reason": self.reason,
        }

    def describe(self) -> str:
        """One sentence naming the field, the operator, both types and the reason."""
        field = f"field {self.field!r}" if self.field else "a condition"
        return (
            f"Cannot compare {field} with {self.operator!r}: {self.reason} "
            f"(fact value is {self.fact_type}, rule value is {self.rule_type})."
        )
