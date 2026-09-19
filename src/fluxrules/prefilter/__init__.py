"""FluxRules pre-filtering layer (in-memory, streaming).

Sits *in front of* the engine so that, at scale, only facts that could
*possibly* match a rule ever reach the CPU-bound ``engine.evaluate()`` call.

Facts in a rule engine are **transient events** that arrive as a stream or in
bulk batches - they are not a queryable dataset. So the pre-screen is a built-
once **in-memory alpha index** (PHREAK style), not a database. Each distinct
leaf predicate ``(field, op, value)`` becomes an alpha node; a streaming fact is
screened in O(distinct predicates + clauses) with no I/O and no materialization.

Soundness contract
------------------
The pre-filter is **sound**: for any fact ``f`` and rule set ``R``, if
``engine.evaluate(f)`` fires any rule, then ``f`` is guaranteed to pass
:meth:`PredicateIndex.matches`. False positives (extra candidates) are allowed
and removed by the exact engine evaluation; false negatives are never allowed.

Public API
----------
- :class:`PredicateExtractor` / :class:`PredicateSet` - derive sound filters from rules.
- :class:`PredicateIndex` - in-memory, streaming alpha-screen (the live path).

Batch / replay path (facts that already live in a DB)
-----------------------------------------------------
The DB-backed pre-filter is valid *only* for re-processing facts already
persisted in a database (backfills, replays, analytics) - never for the live
streaming engine. It is exposed separately so callers cannot mistake it for the
streaming path:

- :class:`FactPreFilterStore` - indexed, backend-agnostic fact store.
- :class:`PreFilteredEvaluator` / :class:`PreFilterStats` - load -> query -> engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fluxrules.prefilter.pipeline import PreFilteredEvaluator, PreFilterStats
from fluxrules.prefilter.predicate import (
    LeafPredicate,
    PredicateExtractor,
    PredicateSet,
    RuleClause,
)
from fluxrules.prefilter.predicate_index import PredicateIndex

if TYPE_CHECKING:  # pragma: no cover
    from fluxrules.prefilter.sql_store import FactPreFilterStore


def __getattr__(name: str) -> Any:
    """Lazily expose the SQLAlchemy-backed store (PEP 562).

    Keeps ``import fluxrules`` free of a hard SQLAlchemy dependency while
    ``from fluxrules.prefilter import FactPreFilterStore`` keeps working.
    """
    if name == "FactPreFilterStore":
        from fluxrules.prefilter.sql_store import FactPreFilterStore

        return FactPreFilterStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Batch / replay path (DB-backed; persisted facts only).
    "FactPreFilterStore",
    # Live streaming path (preferred).
    "LeafPredicate",
    "PreFilterStats",
    "PreFilteredEvaluator",
    "PredicateExtractor",
    "PredicateIndex",
    "PredicateSet",
    "RuleClause",
]
