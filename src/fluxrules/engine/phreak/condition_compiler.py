"""Condition tree compilation.

Compiles a rule's ``condition_dsl`` into a single Python closure
``fn(facts) -> bool``, replacing the per-fact recursive dict-walk in
``PhreakEngine._evaluate_condition_inner`` with structurally-inlined boolean
logic. This is the per-rule speedup that complements the alpha pre-filter:
the alpha layer reduces *which* rules are evaluated; this reduces the cost of
evaluating *each* one.

Safety
------
There is **no arbitrary string ``eval`` of user input**. Boolean structure
(``and`` / ``or`` / ``not`` / ``exists``) is realized as nested Python closures;
every leaf delegates to the exact same :func:`fluxrules.engine.operators.evaluate_operator`
the interpreter uses, with the same hardening flags. So compiled and interpreted
evaluation are guaranteed to agree (a property the parity test enforces).

Unsupported / dynamic node types (``accumulate`` and anything unknown) fall back
to a captured interpreter callable, so compilation never changes results - it
only ever changes speed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Any, Protocol

from fluxrules.engine.operators import evaluate_operator

logger = logging.getLogger(__name__)

# A compiled condition is a unary predicate over the fact dict.
CompiledCondition = Callable[[dict[str, Any]], bool]


class _Flags(Protocol):
    strict_null_handling: bool
    strict_type_comparison: bool
    boolean_string_coercion: bool


def compile_condition(
    condition: dict[str, Any],
    flags: _Flags,
    *,
    fallback_factory: Callable[[dict[str, Any]], Callable[[dict[str, Any]], bool]] | None = None,
    leaf_compiler: Callable[[dict[str, Any], _Flags], CompiledCondition] | None = None,
) -> CompiledCondition:
    """Compile a ``condition_dsl`` tree into a ``fn(facts) -> bool`` closure.

    Args:
        condition: the rule's condition tree (same shape the interpreter walks).
        flags: object exposing ``strict_null_handling`` /
            ``strict_type_comparison`` / ``boolean_string_coercion``.
        fallback_factory: optional callable that, given a *specific sub-condition
            node*, returns an interpreter closure for **that node**. Used for node
            types that cannot be compiled (e.g. ``accumulate``). Must be per-node
            (not the whole root) so a dynamic node nested inside an AND/OR is
            evaluated correctly. If ``None``, such a node compiles to a constant
            ``False`` predicate (matching the interpreter for unknown nodes).
        leaf_compiler: optional callable that, given a *leaf node* and ``flags``,
            returns the closure to evaluate that leaf. The engine supplies a
            **memo-aware** leaf compiler so the compiled boolean structure still
            shares the per-cycle leaf cache (identical ``(field, op, value)``
            leaves are evaluated once across all rules). If ``None``, leaves are
            compiled to a direct :func:`evaluate_operator` call - correct, but
            without the cross-rule memo.

    Returns:
        A closure that evaluates the condition against a fact dict.
    """
    return _compile(condition, flags, fallback_factory, leaf_compiler or _compile_leaf)


def _const(value: bool) -> CompiledCondition:
    return lambda facts: value


def _compile(
    condition: Any,
    flags: _Flags,
    fallback_factory: Callable[[dict[str, Any]], CompiledCondition] | None,
    leaf_compiler: Callable[[dict[str, Any], _Flags], CompiledCondition],
) -> CompiledCondition:
    if not isinstance(condition, dict):
        return _const(False)

    ctype = condition.get("type")

    if ctype == "condition":
        return leaf_compiler(condition, flags)

    if ctype in ("composite", "group", "and", "or"):
        if ctype == "and":
            logic = "AND"
        elif ctype == "or":
            logic = "OR"
        else:
            logic = (condition.get("logic") or condition.get("op", "AND")).upper()
        children = condition.get("conditions") or condition.get("children") or []
        compiled = [_compile(c, flags, fallback_factory, leaf_compiler) for c in children]
        return _compile_bool(logic, compiled)

    if ctype == "not":
        inner = condition.get("condition")
        if inner is not None:
            child = _compile(inner, flags, fallback_factory, leaf_compiler)
            return lambda facts: not child(facts)
        inner_list = condition.get("conditions") or []
        if inner_list:
            compiled = [_compile(c, flags, fallback_factory, leaf_compiler) for c in inner_list]

            # not any(...) -> short-circuit on first True child.
            def _not_any(facts: dict[str, Any]) -> bool:
                for fn in compiled:
                    if fn(facts):
                        return False
                return True

            return _not_any
        return _const(True)

    if ctype == "exists":
        field = condition.get("field")
        if field:
            return lambda facts: field in facts and facts[field] is not None
        inner = condition.get("condition")
        if inner is not None:
            return _compile(inner, flags, fallback_factory, leaf_compiler)
        return _const(False)

    if ctype == "accumulate":
        # Dynamic aggregation - not structurally compilable. Use the interpreter
        # for THIS node to stay correct.
        if fallback_factory is not None:
            return fallback_factory(condition)
        logger.debug("compile_condition: accumulate without fallback -> always False")
        return _const(False)

    # Unknown node type: interpreter returns False here.
    return _const(False)


def _compile_leaf(condition: dict[str, Any], flags: _Flags) -> CompiledCondition:
    """Compile a single leaf to a captured ``evaluate_operator`` call.

    Semantics are preserved exactly by reusing ``evaluate_operator`` with the
    same flags as the interpreter - only the dict lookups and the call's keyword
    binding are hoisted out of the per-fact path.
    """
    field = condition.get("field", "")
    op = condition.get("op", "==")
    value = condition.get("value")

    # Bind the operator call once with all the constant arguments. Per fact we
    # only supply the present-flag and the field value.
    op_call = partial(
        evaluate_operator,
        op,
        rule_value=value,
        strict_null_handling=flags.strict_null_handling,
        strict_type_comparison=flags.strict_type_comparison,
        boolean_string_coercion=flags.boolean_string_coercion,
    )

    def _leaf(facts: dict[str, Any]) -> bool:
        present = field in facts
        return op_call(facts.get(field), field_present=present)

    return _leaf


def _compile_bool(logic: str, compiled: list[CompiledCondition]) -> CompiledCondition:
    """Build a short-circuiting AND/OR over already-compiled children."""
    # Degenerate cases mirror Python's all([]) == True / any([]) == False.
    if logic == "AND":
        if not compiled:
            return _const(True)
        if len(compiled) == 1:
            return compiled[0]

        def _and(facts: dict[str, Any]) -> bool:
            for fn in compiled:
                if not fn(facts):
                    return False
            return True

        return _and

    # OR
    if not compiled:
        return _const(False)
    if len(compiled) == 1:
        return compiled[0]

    def _or(facts: dict[str, Any]) -> bool:
        for fn in compiled:
            if fn(facts):
                return True
        return False

    return _or
