"""Engine infrastructure components.

Internal implementation details for engine implementations.
These are NOT part of the public API.

Public users should use:
    from fluxrules.engine.phreak import PhreakEngine
"""

from fluxrules.engine.infrastructure.agenda import (
    Agenda,
    ConflictResolutionStrategy,
    SalienceRecencyStrategy,
)
from fluxrules.engine.infrastructure.bitmask_linker import (
    BitMaskLinker,
    RuleLinkInfo,
    SegmentBitInfo,
)
from fluxrules.engine.infrastructure.engine_metrics import (
    EngineMetrics,
    LatencyReservoir,
)
from fluxrules.engine.infrastructure.evaluation_filter import EvaluationFilter
from fluxrules.engine.infrastructure.evaluation_result import EvaluationResult
from fluxrules.engine.infrastructure.field_index import FieldIndex
from fluxrules.engine.infrastructure.global_rule_repository import (
    GlobalRuleRepository,
    normalize_rule,
)
from fluxrules.engine.infrastructure.lazy_evaluation import LazyEvaluationMixin
from fluxrules.engine.infrastructure.node_memory import NodeMemory
from fluxrules.engine.infrastructure.segment_network import SegmentNetwork
from fluxrules.engine.infrastructure.token_propagator import TokenPropagator
from fluxrules.engine.infrastructure.working_memory import UnifiedWorkingMemory

__all__ = [
    "Agenda",
    "BitMaskLinker",
    "ConflictResolutionStrategy",
    "EngineMetrics",
    "EvaluationFilter",
    "EvaluationResult",
    "FieldIndex",
    "GlobalRuleRepository",
    "LatencyReservoir",
    "LazyEvaluationMixin",
    "NodeMemory",
    "Rule",
    "RuleLinkInfo",
    "RuntimeRule",
    "SalienceRecencyStrategy",
    "SegmentBitInfo",
    "SegmentNetwork",
    "TokenPropagator",
    "UnifiedWorkingMemory",
    "normalize_rule",
]


def __getattr__(name: str):
    """Forward the deprecated ``Rule`` / ``RuntimeRule`` aliases.

    Re-exporting them eagerly would silence the deprecation warning, so
    resolution is deferred to ``global_rule_repository.__getattr__``, which
    owns the deprecation.
    """
    if name in ("Rule", "RuntimeRule"):
        from fluxrules.engine.infrastructure import global_rule_repository

        return getattr(global_rule_repository, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
