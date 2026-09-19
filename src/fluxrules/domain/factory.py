"""Factory functions for converting dicts to domain models."""

from __future__ import annotations

import warnings
from typing import Any

from fluxrules.domain.errors import LossyConditionViewWarning
from fluxrules.domain.models import ConditionView, EngineRule, RuleCondition, Ruleset


def rule_from_dict(data: dict[str, Any]) -> EngineRule:
    """Convert a rule dict to a ``Rule`` domain object.

    Supports two dict formats:

    **DSL format** (used by ``RuleEngine``)::

        {"id": 1, "name": "...", "condition_dsl": {...}, "action": "...", ...}

    **Native format** (used by the reference evaluator)::

        {"id": 1, "name": "...", "conditions": [...], "actions": [...], ...}

    Raises:
        ValueError: If the dict is missing required fields or is malformed.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    rule_id = data.get("id")
    name = data.get("name")
    if rule_id is None or name is None:
        raise ValueError(f"Rule dict must contain 'id' and 'name'. Got keys: {sorted(data.keys())}")

    # Parse conditions from either format
    conditions: tuple[RuleCondition, ...] = ()

    if "conditions" in data:
        # Native format: list of condition dicts
        raw_conditions = data["conditions"]
        if not isinstance(raw_conditions, (list, tuple)):
            raise ValueError("'conditions' must be a list of condition dicts")
        conditions = tuple(
            RuleCondition(
                fact=c["fact"],
                operator=c["operator"],
                value=c.get("value"),
            )
            for c in raw_conditions
        )

    # For the DSL format the tree is the authoritative logic and is passed
    # through untouched; the flat ``conditions`` view is derived lazily by
    # ``EngineRule`` on demand, so it is not extracted eagerly here (doing so
    # would emit a lossy-view warning for OR/nested trees during construction).

    # Parse actions
    actions: tuple[str, ...] = ()
    if "actions" in data:
        raw_actions = data["actions"]
        actions = (
            tuple(raw_actions) if isinstance(raw_actions, (list, tuple)) else (str(raw_actions),)
        )
    elif "action" in data:
        actions = (str(data["action"]),)

    return EngineRule(
        id=int(rule_id),
        name=str(name),
        conditions=conditions,
        actions=actions,
        priority=int(data.get("priority", 0)),
        group=str(data.get("group", "")),
        description=str(data.get("description", "")),
        enabled=bool(data.get("enabled", True)),
        condition_dsl=data.get("condition_dsl")
        if isinstance(data.get("condition_dsl"), dict)
        else None,
    )


def ruleset_from_dict(data: dict[str, Any]) -> Ruleset:
    """Convert a ruleset dict to a ``Ruleset`` domain object.

    Expected format::

        {"group": "...", "rules": [{...}, ...]}

    Also accepts ``"name"`` as an alias for ``"group"``.

    Raises:
        ValueError: If the dict is missing required fields.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    rs_group = data.get("group") or data.get("name")
    if rs_group is None:
        raise ValueError(
            f"Ruleset dict must contain 'group' (or 'name'). Got keys: {sorted(data.keys())}"
        )

    raw_rules = data.get("rules", [])
    rules = tuple(rule_from_dict(r) for r in raw_rules)

    return Ruleset(group=str(rs_group), rules=rules)


def _extract_conditions_from_dsl(
    dsl: dict[str, Any],
) -> ConditionView:
    """Recursively extract ``RuleCondition`` objects from a DSL tree.

    The result is a **flat conjunction** and therefore a lossy view of the DSL:
    ``or`` / ``not`` nodes cannot be represented. When one is encountered the
    leaves found are still returned, a
    :class:`~fluxrules.domain.errors.LossyConditionViewWarning` is emitted, and
    the returned :class:`~fluxrules.domain.models.ConditionView` is flagged
    ``lossy`` so callers that rebuild a tree cannot mistake it for a genuine
    conjunction. ``()`` is returned only for genuinely empty input.

    The canonical representation of rule logic is always ``condition_dsl``;
    this view exists for the reference evaluator and simple validators only.
    """
    if not isinstance(dsl, dict):
        return ConditionView()

    ctype = dsl.get("type")

    if ctype == "condition":
        return ConditionView(
            (
                RuleCondition(
                    fact=dsl["field"],
                    operator=dsl["op"],
                    value=dsl.get("value"),
                ),
            )
        )

    # Composite nodes - recurse into children.
    # ``and``/``or`` are the node types the engines evaluate; ``group``/
    # ``composite`` are the equivalent authoring shapes. Omitting any of them
    # here makes conditions vanish and the rule match nothing.
    children: list[dict[str, Any]] = []
    if ctype in ("group", "and", "or"):
        children = dsl.get("children", []) or dsl.get("conditions", []) or []
    elif ctype == "composite":
        children = dsl.get("conditions", []) or dsl.get("children", []) or []
    elif ctype == "not":
        children = dsl.get("children", []) or []
        child = dsl.get("child")
        if child is not None:
            children = [child]

    lossy = ctype == "not" or (
        ctype == "or"
        or (ctype in ("group", "composite") and str(dsl.get("op", "")).upper() in ("OR", "NOT"))
    )
    if lossy:
        warnings.warn(
            f"DSL node of type {ctype!r} cannot be represented by the flat "
            "condition view; its boolean structure is lost. Use "
            "'condition_dsl' for rule logic.",
            LossyConditionViewWarning,
            stacklevel=2,
        )

    result: list[RuleCondition] = []
    for child in children:
        extracted = _extract_conditions_from_dsl(child)
        # Loss anywhere in the subtree taints the whole view: an AND whose
        # child is an OR is no more reconstructible than the OR itself.
        lossy = lossy or getattr(extracted, "lossy", False)
        result.extend(extracted)
    return ConditionView(result, lossy=lossy)
