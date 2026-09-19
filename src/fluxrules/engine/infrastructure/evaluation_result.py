"""Evaluation result returned by RuleEngine.evaluate()."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

_DEPRECATION = (
    "EvaluationResult.matched_rule_ids is deprecated; use 'candidate_rule_ids' "
    "(rules considered for a fact) or 'fired_rules' (rules that actually "
    "matched). The field never meant 'matched': discovery is a prefilter that "
    "may report rules here whose conditions later fail."
)


@dataclass
class EvaluationResult:
    """Result of a unified engine evaluation.

    Attributes:
        candidate_rule_ids: IDs of rules **considered** for this fact - the
            discovery/prefilter output, produced before conditions are fully
            evaluated. A superset of ``fired_rules`` that may contain rules
            which did not match. Use ``fired_rules`` to learn what matched.
        fired_rules: IDs of rules that were actually fired (after agenda).
        rules_by_domain: Fired rules grouped by domain.
        rules_by_tag: Fired rules grouped by tag.
        fired_segments: Segment IDs that were evaluated.
        latency_ms: Total evaluation latency in milliseconds.
        engine_type: Name of the concrete engine class.
        actions: Collected actions from fired rules.
        explanations: Per-rule explanations.
    """

    candidate_rule_ids: list[int] = field(default_factory=list)
    fired_rules: list[int] = field(default_factory=list)
    rules_by_domain: dict[str, list[int]] = field(default_factory=dict)
    rules_by_tag: dict[str, list[int]] = field(default_factory=dict)
    fired_segments: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    engine_type: str = ""
    actions: list[str] = field(default_factory=list)
    explanations: dict[int, str] = field(default_factory=dict)

    @property
    def matched_rule_ids(self) -> list[int]:
        """Deprecated alias for :attr:`candidate_rule_ids`."""
        warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
        return self.candidate_rule_ids

    @matched_rule_ids.setter
    def matched_rule_ids(self, value: list[int]) -> None:
        warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
        self.candidate_rule_ids = value


# The dataclass machinery generates ``__init__`` after the class body executes,
# so the deprecated-keyword shim has to wrap it here rather than be defined
# above (a dataclass cannot express "two accepted names for one field").
_generated_init = EvaluationResult.__init__


def _init_with_deprecated_kwarg(self: EvaluationResult, *args: Any, **kwargs: Any) -> None:
    if "matched_rule_ids" in kwargs:
        if "candidate_rule_ids" in kwargs:
            raise TypeError(
                "Pass either 'candidate_rule_ids' or the deprecated 'matched_rule_ids', not both."
            )
        warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
        kwargs["candidate_rule_ids"] = kwargs.pop("matched_rule_ids")
    _generated_init(self, *args, **kwargs)


_init_with_deprecated_kwarg.__doc__ = _generated_init.__doc__
EvaluationResult.__init__ = _init_with_deprecated_kwarg  # type: ignore[method-assign]
