"""PHREAK Engine - Lazy evaluation with integrated optimizations.

The PHREAK engine implements lazy evaluation with dirty tracking:

- Lazy evaluation: only evaluate rules whose segments are dirty
- Dirty tracking: track which fields changed
- Field indexing: efficient lookup of affected rules
- Segment network: hierarchical rule organization

Usage:
    from fluxrules.engine.phreak import PhreakEngine
    # or
    from fluxrules.engine.phreak import PhreakEngine

Characteristics:
    - Lazy evaluation (only process changed facts / dirty segments)
    - Dirty tracking (track field modifications via FieldIndex)
    - Field indexing (find affected rules efficiently)
    - Segment network (hierarchical rule organization)
    - Conflict resolution (agenda-based, salience + recency)

Ideal for:
    - Streaming data (facts arriving incrementally)
    - Large numbers of facts with few changes
    - Complex rule dependencies
    - When latency matters more than throughput

Internal Structure:
    _engine.py: Core PhreakEngine implementation
"""

from fluxrules.engine.phreak._engine import PhreakEngine

__all__ = ["PhreakEngine"]
