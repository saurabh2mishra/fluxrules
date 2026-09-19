"""Cross-fact join engine.

A **separate** engine from the single-fact ``PhreakEngine``: it retains many
typed facts in working memory and matches tuples of facts across patterns, with
incremental truth maintenance on insert/update/retract.

This is the capability the single-fact guardrail (``scope_guard.py``)
deliberately rejects for ``PhreakEngine``. Use it only when correlation genuinely
cannot be pushed upstream - see
``.research/PHREAK_P3_PLAN_CROSS_FACT_NETWORK.md`` and
``docs/engine-scope-and-limits.md``.

Public API::

    from fluxrules.engine.cross_fact import (
        CrossFactEngine, CrossFactRule, Pattern, AlphaConstraint, JoinConstraint,
        Exists, Accumulate, TemporalConstraint,
    )
"""

from fluxrules.engine.cross_fact._engine import CrossFactDelta, CrossFactEngine
from fluxrules.engine.cross_fact.models import (
    Accumulate,
    Activation,
    AlphaConstraint,
    CrossFactRule,
    Exists,
    FactHandle,
    JoinConstraint,
    Pattern,
    TemporalConstraint,
)
from fluxrules.engine.cross_fact.working_memory import CrossFactWorkingMemory

__all__ = [
    "Accumulate",
    "Activation",
    "AlphaConstraint",
    "CrossFactDelta",
    "CrossFactEngine",
    "CrossFactRule",
    "CrossFactWorkingMemory",
    "Exists",
    "FactHandle",
    "JoinConstraint",
    "Pattern",
    "TemporalConstraint",
]
