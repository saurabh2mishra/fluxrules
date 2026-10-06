"""Re-export of the single :class:`EvaluationResult` type.

This module used to define a *second* ``EvaluationResult`` whose
``matched_rule_ids`` meant "candidates considered", while the domain type's
field of the same name meant "rules that fired". Two classes, one name, opposite
meanings. They are now one class, owned by the domain layer, and imported here
so ``from fluxrules.engine.infrastructure import EvaluationResult`` keeps
resolving to it.
"""

from __future__ import annotations

from fluxrules.domain.models import EvaluationResult

__all__ = ["EvaluationResult"]
