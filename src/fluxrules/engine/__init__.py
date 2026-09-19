"""Engine types for FluxRules rule evaluation.

RECOMMENDED USAGE - Import the engine directly from its package:

    from fluxrules.engine.phreak import PhreakEngine

This is the canonical way to import the engine implementation. FluxRules is
built on the PHREAK algorithm - a lazy, agenda-driven evaluation strategy that
is both memory-efficient and fast at scale.

For infrastructure types (not engine implementations):

    from fluxrules.engine import (
        BaseEngine,
        EvaluationFilter,
        EvaluationResult,
        Rule,
    )

Engine Types:
    PhreakEngine: Lazy PHREAK evaluation (the FluxRules engine)
        Import from: fluxrules.engine.phreak
    BaseEngine: Abstract base class for implementing custom engines
        Import from: fluxrules.engine

Infrastructure Types:
    EvaluationFilter, EvaluationResult, Rule: Shared types across engines
        Import from: fluxrules.engine
"""

from fluxrules.engine.base import BaseEngine

# Re-export infrastructure types needed by users
from fluxrules.engine.infrastructure import (
    EvaluationFilter,
    EvaluationResult,
)

# Import engine locally for get_engine() registry (not exported in __all__)
from fluxrules.engine.operator_registry import OperatorRegistry, register_operator
from fluxrules.engine.phreak import PhreakEngine as _PhreakEngine
from fluxrules.engine.profiler import RuleProfiler

__all__ = [
    "BaseEngine",
    "EvaluationFilter",
    "EvaluationResult",
    "OperatorRegistry",
    "Rule",
    "RuleProfiler",
    "RuntimeRule",
    "get_available_engines",
    "get_engine",
    "register_engine",
    "register_operator",
    "unregister_engine",
]


_ENGINE_REGISTRY: dict[str, type[BaseEngine]] = {
    "PHREAK": _PhreakEngine,
}

#: Engines shipped with FluxRules. These can never be overridden or removed
#: through the public registration API, so ``get_engine("PHREAK")`` is stable.
_BUILTIN_ENGINES = frozenset({"PHREAK"})


def register_engine(name: str, engine_cls: type[BaseEngine], *, override: bool = False) -> None:
    """Register a custom engine class under a selectable name.

    Once registered, ``name`` is usable everywhere the built-in ``"PHREAK"``
    engine is: :func:`get_engine`, the HTTP ``/api/v1/engines`` routes, and the
    ``fluxrules`` CLI ``--engine`` option.

    Args:
        name: Case-insensitive selector (stored upper-cased).
        engine_cls: A concrete :class:`BaseEngine` subclass.
        override: Allow replacing an existing *custom* registration. Built-in
            engines can never be overridden.

    Raises:
        TypeError: If ``engine_cls`` is not a ``BaseEngine`` subclass.
        ValueError: If ``name`` is blank, targets a built-in engine, or already
            exists without ``override=True``.
    """
    if not name or not name.strip():
        raise ValueError("Engine name must be a non-empty string.")
    if not (isinstance(engine_cls, type) and issubclass(engine_cls, BaseEngine)):
        raise TypeError(f"engine_cls must be a BaseEngine subclass, got {engine_cls!r}.")
    key = name.strip().upper()
    if key in _BUILTIN_ENGINES:
        raise ValueError(f"Cannot override the built-in engine {key!r}.")
    if key in _ENGINE_REGISTRY and not override:
        raise ValueError(f"Engine {key!r} is already registered; pass override=True to replace it.")
    _ENGINE_REGISTRY[key] = engine_cls


def unregister_engine(name: str) -> None:
    """Remove a previously registered custom engine.

    Built-in engines cannot be removed; unknown names are ignored.

    Raises:
        ValueError: If ``name`` targets a built-in engine.
    """
    key = name.strip().upper()
    if key in _BUILTIN_ENGINES:
        raise ValueError(f"Cannot unregister the built-in engine {key!r}.")
    _ENGINE_REGISTRY.pop(key, None)


def get_engine(engine_type: str = "PHREAK", **kwargs) -> BaseEngine:
    """Create an engine instance by type name."""
    key = engine_type.upper()
    if key not in _ENGINE_REGISTRY:
        raise ValueError(
            f"Unknown engine type: {engine_type!r}. Available: {list(_ENGINE_REGISTRY)}"
        )
    return _ENGINE_REGISTRY[key](**kwargs)


def get_available_engines() -> list[str]:
    """Return list of available engine type names."""
    return list(_ENGINE_REGISTRY)


def get_cross_fact_engine(**kwargs):
    """Create a cross-fact :class:`~fluxrules.engine.cross_fact.CrossFactEngine` (P3 Track B).

    The beta engine is **not** part of the single-fact ``BaseEngine`` registry: it
    has a different, *stateful* multi-fact contract (``insert`` / ``update`` /
    ``retract`` returning activation deltas) rather than
    ``evaluate(facts: dict)``. It is exposed via this dedicated factory - and kept
    out of ``get_engine`` - precisely so the two contracts never get confused.

    Use it only when correlation genuinely cannot be pushed upstream; see
    ``docs/engine-scope-and-limits.md``. For request/response single-fact scoring,
    use ``get_engine("PHREAK")``.
    """
    from fluxrules.engine.cross_fact import CrossFactEngine

    return CrossFactEngine(**kwargs)


def __getattr__(name: str):
    """Forward the deprecated ``Rule`` / ``RuntimeRule`` aliases.

    Deferred so accessing them still raises the ``DeprecationWarning`` owned
    by ``global_rule_repository``.
    """
    if name in ("Rule", "RuntimeRule"):
        from fluxrules.engine import infrastructure

        return getattr(infrastructure, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
