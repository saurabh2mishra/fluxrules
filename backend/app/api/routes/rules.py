from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
import json
from app.database import get_db
from app.schemas.rule import (
    RuleCreate, RuleUpdate, RuleResponse, RuleVersionResponse,
    SimulateRequest, SimulateResponse, DependencyGraph, ConflictReport
)
from app.services.rule_service import RuleService
from app.api.deps import get_current_user, get_current_admin
from app.models.user import User
from app.models.rule import Rule
from app.engine.rete_engine import ReteEngine
from app.engine.optimized_rete_engine import OptimizedReteEngine, RuleCache
from app.engine.dependency_graph import DependencyGraphBuilder
from app.services.rule_validation_service import RuleValidationService

from app.engine.actions import get_available_actions

from app.models.conflicted_rule import ConflictedRule
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

router = APIRouter(prefix="/rules", tags=["rules"])


# ---------------------------------------------------------------------------
# Inline conflict detection helpers (replaces removed services.conflict_detector)
# Uses the optimized RETE engine for rule caching and evaluation.
# ---------------------------------------------------------------------------

def _detect_all_conflicts(db: Session) -> Dict:
    """Detect duplicate conditions and priority collisions across all rules."""
    cache = RuleCache()
    rules = cache.get_rules(db)

    conflicts = []
    # Duplicate conditions
    condition_map: dict = {}
    for rule in rules:
        condition_str = json.dumps(rule["condition_dsl"], sort_keys=True)
        if condition_str in condition_map:
            prev = condition_map[condition_str]
            conflicts.append({
                "type": "duplicate_condition",
                "rule1_id": prev["id"],
                "rule1_name": prev["name"],
                "rule2_id": rule["id"],
                "rule2_name": rule["name"],
                "description": (
                    f"Rules '{prev['name']}' (ID: {prev['id']}) and "
                    f"'{rule['name']}' (ID: {rule['id']}) have identical conditions"
                ),
            })
        else:
            condition_map[condition_str] = rule

    # Priority collisions
    priority_map: dict = {}
    for rule in rules:
        key = (rule["group"] or "default", rule["priority"])
        priority_map.setdefault(key, []).append(rule)

    for (group, priority), rule_list in priority_map.items():
        if len(rule_list) > 1:
            rule_names = ", ".join(f"'{r['name']}' (ID: {r['id']})" for r in rule_list)
            conflicts.append({
                "type": "priority_collision",
                "group": group,
                "priority": priority,
                "rules": rule_list,
                "description": f"Multiple rules in group '{group}' have priority {priority}: {rule_names}",
            })

    return {"conflicts": conflicts}


def _check_new_rule_conflicts(db: Session, new_rule) -> list:
    """Check conflicts for a new rule (used in parked-rule resolution)."""
    engine = OptimizedReteEngine(db)
    rules = engine.cache.get_rules(db)

    conflicts: list = []
    event = new_rule.condition_dsl if isinstance(new_rule.condition_dsl, dict) else json.loads(new_rule.condition_dsl)
    result = engine.evaluate(event, use_rete=True)
    matched_rules = result.get("matched_rules", [])
    new_condition = json.dumps(event, sort_keys=True)

    for rule in matched_rules:
        existing = next((r for r in rules if r["id"] == rule["id"]), None)
        if existing:
            if json.dumps(existing["condition_dsl"], sort_keys=True) == new_condition:
                conflicts.append({
                    "type": "duplicate_condition",
                    "existing_rule_id": rule["id"],
                    "existing_rule_name": rule["name"],
                    "description": f"Identical condition exists in rule '{rule['name']}' (ID: {rule['id']})",
                })

    # Priority collision
    new_group = new_rule.group or "default"
    new_priority = new_rule.priority
    priority_map: dict = {}
    for rule in rules:
        key = (rule["group"] or "default", rule["priority"])
        priority_map.setdefault(key, []).append(rule)

    for rule in priority_map.get((new_group, new_priority), []):
        conflicts.append({
            "type": "priority_collision",
            "existing_rule_id": rule["id"],
            "existing_rule_name": rule["name"],
            "group": new_group,
            "priority": new_priority,
            "description": f"Rule '{rule['name']}' (ID: {rule['id']}) has same priority {new_priority} in group '{new_group}'",
        })

    return conflicts


@router.get("/actions/available")
def list_available_actions(
    current_user: User = Depends(get_current_user)
):
    """Get list of all available action functions that can be used in rules"""
    actions = get_available_actions()
    
    # Group by category
    categorized = {}
    for action in actions:
        category = action["category"]
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(action)
    
    return {
        "actions": actions,
        "categorized": categorized,
        "total": len(actions)
    }

def serialize_rule(rule: Rule) -> dict:
    """Convert Rule model to dict with proper JSON parsing"""
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "group": rule.group,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "condition_dsl": json.loads(rule.condition_dsl) if isinstance(rule.condition_dsl, str) else rule.condition_dsl,
        "action": rule.action,
        "rule_metadata": json.loads(rule.rule_metadata) if rule.rule_metadata and isinstance(rule.rule_metadata, str) else rule.rule_metadata,
        "current_version": rule.current_version,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
        "created_by": rule.created_by
    }

@router.get("", response_model=List[RuleResponse])
def list_rules(
    skip: int = 0,
    limit: int = 100,
    group: Optional[str] = None,
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = RuleService(db)
    rules = service.list_rules(skip=skip, limit=limit, group=group, enabled=enabled)
    return [serialize_rule(rule) for rule in rules]


@router.get("/groups")
def get_rule_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all unique rule groups for dropdown"""
    groups = db.query(Rule.group).distinct().all()
    # Flatten and filter out None/empty
    return {"groups": [g[0] for g in groups if g[0]]}


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = RuleService(db)
    rule = service.get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return serialize_rule(rule)

@router.post("/validate", response_model=dict)
def validate_rule(
    rule: RuleCreate = Body(...),
    rule_id: Optional[int] = Query(None, description="ID of rule being edited (for edit validation)", alias="rule_id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate a rule before saving - check for conflicts, duplicates, and similar rules"""
    validator = RuleValidationService(db)
    validation_result = validator.validate(rule.model_dump(), rule_id=rule_id)
    conflicts = list(validation_result.get("conflicts", []))

    # Check for exact duplicate name, ignoring self if editing
    duplicate = db.query(Rule).filter(Rule.name == rule.name).first()
    duplicate_conflict = None
    if duplicate and (rule_id is None or duplicate.id != rule_id):
        duplicate_conflict = {
            "type": "duplicate_name",
            "description": f"A rule with the name '{rule.name}' already exists.",
            "existing_rule_id": duplicate.id,
            "existing_rule_name": duplicate.name
        }
        conflicts.append(duplicate_conflict)

    # Find similar rules (same group or similar conditions)
    similar_rules = []
    existing_rules = db.query(Rule).filter(Rule.enabled == True).all()
    for existing in existing_rules:
        # Skip the rule being edited — it should never appear as "similar to itself"
        if rule_id is not None and existing.id == rule_id:
            continue
        similarity_score = 0
        reasons = []
        # Check if same group
        if (rule.group and existing.group and rule.group == existing.group):
            similarity_score += 30
            reasons.append(f"Same group: '{rule.group}'")
        # Check if similar name
        if rule.name and existing.name:
            name_lower = rule.name.lower()
            existing_lower = existing.name.lower()
            if name_lower in existing_lower or existing_lower in name_lower:
                similarity_score += 20
                reasons.append("Similar name")
        # Check for overlapping fields in conditions
        try:
            new_fields = extract_fields(rule.condition_dsl)
            existing_dsl = json.loads(existing.condition_dsl) if isinstance(existing.condition_dsl, str) else existing.condition_dsl
            existing_fields = extract_fields(existing_dsl)
            common_fields = new_fields & existing_fields
            if common_fields:
                similarity_score += len(common_fields) * 10
                reasons.append(f"Common fields: {', '.join(common_fields)}")
        except Exception:
            pass
        if similarity_score >= 30:
            similar_rules.append({
                "rule_id": existing.id,
                "rule_name": existing.name,
                "group": existing.group,
                "similarity_score": similarity_score,
                "reasons": reasons
            })
    # Sort by similarity score
    similar_rules.sort(key=lambda x: x["similarity_score"], reverse=True)

    # Safety net: strip any self-referencing conflicts/similar rules
    if rule_id is not None:
        conflicts = [
            c for c in conflicts
            if str(c.get("existing_rule_id")) != str(rule_id)
        ]
        similar_rules = [
            s for s in similar_rules
            if str(s.get("rule_id")) != str(rule_id)
        ]

    response = {
        "valid": len(conflicts) == 0,
        "conflicts": conflicts,
        "duplicate_conflict": duplicate_conflict,
        "similar_rules": similar_rules[:5],  # Top 5 similar rules
        "brms_report": validation_result.get("brms_report"),
    }
    return response

def extract_fields(condition_dsl: dict) -> set:
    """Extract all field names from a condition DSL"""
    fields = set()
    if not condition_dsl:
        return fields
    
    if condition_dsl.get("type") == "condition" and condition_dsl.get("field"):
        fields.add(condition_dsl["field"])
    
    if condition_dsl.get("children"):
        for child in condition_dsl["children"]:
            fields.update(extract_fields(child))
    
    return fields

@router.post("", response_model=RuleResponse)
@router.post("/", response_model=RuleResponse)
def create_rule(
    rule: RuleCreate,
    skip_conflict_check: bool = Query(False, description="Skip conflict checking for faster creation"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check for conflicts BEFORE creating (unless skipped for bulk operations)
    if not skip_conflict_check:
        validation_result = RuleValidationService(db).validate(rule.model_dump())
        potential_conflicts = validation_result.get("conflicts", [])

        # Block creation for any meaningful conflict (duplicate condition,
        # priority collision, dead rule, or BRMS overlap).
        # brms_overlap means two rules fire on overlapping inputs — only one
        # should be active at a time; the newcomer is parked for review.
        BLOCKING_CONFLICT_TYPES = {"priority_collision", "duplicate_condition", "brms_dead_rule", "brms_overlap"}
        blocking_conflicts = [
            c for c in potential_conflicts
            if c.get("type") in BLOCKING_CONFLICT_TYPES and (c.get("existing_rule_id") is not None or c.get("type") == "brms_dead_rule")
        ]

        if blocking_conflicts:
            # Park the rejected rule for business review
            for conflict in blocking_conflicts:
                parked = ConflictedRule(
                    name=rule.name,
                    description=rule.description,
                    group=rule.group,
                    priority=rule.priority,
                    enabled=rule.enabled,
                    condition_dsl=json.dumps(rule.condition_dsl) if not isinstance(rule.condition_dsl, str) else rule.condition_dsl,
                    action=rule.action,
                    rule_metadata=json.dumps(rule.rule_metadata) if rule.rule_metadata else None,
                    conflict_type=conflict.get("type", "unknown"),
                    conflict_description=conflict.get("description", ""),
                    conflicting_rule_id=conflict.get("existing_rule_id"),
                    conflicting_rule_name=conflict.get("existing_rule_name"),
                    new_rule_id=getattr(rule, 'id', None),
                    submitted_by=current_user.id,
                    status="pending"
                )
                db.add(parked)
            db.commit()
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Rule conflicts detected. The rule has been parked for business review.",
                    "conflicts": blocking_conflicts,
                    "parked": True
                }
            )
    
    # Invalidate conflict cache after creating
    invalidate_conflict_cache(db)
    
    service = RuleService(db)
    created_rule = service.create_rule(rule, current_user.id)
    return serialize_rule(created_rule)


@router.post("/bulk", response_model=List[RuleResponse])
def bulk_create_rules(
    rules: List[RuleCreate],
    validate_conflicts: bool = Query(True, description="Run conflict checks and park conflicting rules"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create multiple rules in a single request.
    Conflicting rules are parked (same behavior as single create).
    """
    service = RuleService(db)
    created_rules = []
    errors = []

    for i, rule in enumerate(rules):
        try:
            if validate_conflicts:
                validation_result = RuleValidationService(db).validate(rule.model_dump())
                potential_conflicts = validation_result.get("conflicts", [])
                blocking_types = {"priority_collision", "duplicate_condition", "brms_dead_rule", "brms_overlap"}
                blocking_conflicts = [
                    c for c in potential_conflicts
                    if c.get("type") in blocking_types and (c.get("existing_rule_id") is not None or c.get("type") == "brms_dead_rule")
                ]

                if blocking_conflicts:
                    for conflict in blocking_conflicts:
                        parked = ConflictedRule(
                            name=rule.name,
                            description=rule.description,
                            group=rule.group,
                            priority=rule.priority,
                            enabled=rule.enabled,
                            condition_dsl=json.dumps(rule.condition_dsl) if not isinstance(rule.condition_dsl, str) else rule.condition_dsl,
                            action=rule.action,
                            rule_metadata=json.dumps(rule.rule_metadata) if rule.rule_metadata else None,
                            conflict_type=conflict.get("type", "unknown"),
                            conflict_description=conflict.get("description", ""),
                            conflicting_rule_id=conflict.get("existing_rule_id"),
                            conflicting_rule_name=conflict.get("existing_rule_name"),
                            new_rule_id=getattr(rule, 'id', None),
                            submitted_by=current_user.id,
                            status="pending"
                        )
                        db.add(parked)
                    db.commit()
                    errors.append({
                        "index": i,
                        "rule_name": rule.name,
                        "error": "Rule conflicts detected. Rule parked for review.",
                        "parked": True,
                        "conflicts": blocking_conflicts,
                    })
                    continue

            created_rule = service.create_rule(rule, current_user.id)
            created_rules.append(jsonable_encoder(serialize_rule(created_rule)))
        except Exception as e:
            errors.append({"index": i, "rule_name": rule.name, "error": str(e)})

    # Invalidate cache after bulk operation
    invalidate_conflict_cache(db)

    if errors:
        raise HTTPException(
            status_code=207,  # Multi-Status
            detail={
                "message": f"Created {len(created_rules)} rules, {len(errors)} failed",
                "created": created_rules,
                "errors": errors
            }
        )

    return created_rules

@router.put("/{rule_id}", response_model=RuleResponse)
def update_rule(
    rule_id: int,
    rule_update: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check for conflicts BEFORE updating — use the same blocking types as create
    validation_result = RuleValidationService(db).validate(rule_update.model_dump(exclude_none=True), rule_id=rule_id)
    potential_conflicts = validation_result.get("conflicts", [])

    BLOCKING_CONFLICT_TYPES = {"priority_collision", "duplicate_condition", "brms_dead_rule", "brms_overlap"}
    blocking_conflicts = [
        c for c in potential_conflicts
        if c.get("type") in BLOCKING_CONFLICT_TYPES
        and (c.get("existing_rule_id") is not None or c.get("type") == "brms_dead_rule")
    ]

    if blocking_conflicts:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Rule conflicts detected. Please resolve before updating.",
                "conflicts": blocking_conflicts
            }
        )
    
    service = RuleService(db)
    rule = service.update_rule(rule_id, rule_update, current_user.id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return serialize_rule(rule)

@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    service = RuleService(db)
    if not service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted successfully"}

@router.get("/{rule_id}/versions", response_model=List[RuleVersionResponse])
def list_rule_versions(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = RuleService(db)
    versions = service.get_rule_versions(rule_id)
    return [
        {
            **version.__dict__,
            "condition_dsl": json.loads(version.condition_dsl) if isinstance(version.condition_dsl, str) else version.condition_dsl,
            "rule_metadata": json.loads(version.rule_metadata) if version.rule_metadata and isinstance(version.rule_metadata, str) else version.rule_metadata
        }
        for version in versions
    ]

@router.get("/{rule_id}/versions/{version}", response_model=RuleVersionResponse)
def get_rule_version(
    rule_id: int,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = RuleService(db)
    rule_version = service.get_rule_version(rule_id, version)
    if not rule_version:
        raise HTTPException(status_code=404, detail="Rule version not found")
    return {
        **rule_version.__dict__,
        "condition_dsl": json.loads(rule_version.condition_dsl) if isinstance(rule_version.condition_dsl, str) else rule_version.condition_dsl,
        "rule_metadata": json.loads(rule_version.rule_metadata) if rule_version.rule_metadata and isinstance(rule_version.rule_metadata, str) else rule_version.rule_metadata
    }

@router.get("/{rule_id}/diff/{version1}/{version2}")
def get_version_diff(
    rule_id: int,
    version1: int,
    version2: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = RuleService(db)
    diff = service.get_version_diff(rule_id, version1, version2)
    if not diff:
        raise HTTPException(status_code=404, detail="Versions not found")
    return diff

@router.post("/simulate", response_model=SimulateResponse)
def simulate_event(
    request: SimulateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = RuleService(db)
    engine = ReteEngine(db)
    return engine.simulate(request.event, request.rule_ids)

@router.post("/reload")
def reload_engine(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    engine = ReteEngine(db)
    engine.reload_rules()
    return {"message": "Engine reloaded successfully", "optimized": engine._optimized_engine is not None}

@router.get("/engine/stats")
def get_engine_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get engine performance statistics."""
    engine = ReteEngine(db)
    
    stats = {
        "engine_type": "optimized" if engine._optimized_engine else "simple",
        "optimized_available": engine._optimized_engine is not None
    }
    
    if engine._optimized_engine:
        stats.update(engine._optimized_engine.get_stats())
    
    return stats

@router.post("/engine/invalidate-cache")
def invalidate_engine_cache(
    group: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """Invalidate rule cache (admin only)."""
    engine = ReteEngine(db)
    
    if engine._optimized_engine:
        engine._optimized_engine.invalidate_cache(group)
        return {"message": f"Cache invalidated for group: {group or 'all'}", "success": True}
    else:
        return {"message": "Optimized engine not available, no cache to invalidate", "success": False}

@router.get("/graph/dependencies/legacy", response_model=DependencyGraph)
def get_dependency_graph_legacy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Legacy full-graph endpoint retained for backward compatibility and debugging."""
    builder = DependencyGraphBuilder(db)
    return builder.build_graph()

@router.get("/conflicts/detect", response_model=ConflictReport)
def detect_conflicts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = _detect_all_conflicts(db)
    try:
        # Clear previous detected conflicts (status='detected')
        db.query(ConflictedRule).filter(ConflictedRule.status == 'detected').delete()
        db.commit()
        # Prepare ConflictedRule objects for bulk insert
        to_insert = []
        for conflict in result.get("conflicts", []):
            if conflict["type"] == "duplicate_condition":
                to_insert.append(ConflictedRule(
                    name=conflict["rule2_name"],
                    description=conflict["description"],
                    group=None,
                    priority=None,
                    enabled=True,
                    condition_dsl="{}",  # Not available here
                    action="",
                    rule_metadata=None,
                    conflict_type=conflict["type"],
                    conflict_description=conflict["description"],
                    conflicting_rule_id=conflict["rule1_id"],
                    conflicting_rule_name=conflict["rule1_name"],
                    status="detected"
                ))
            elif conflict["type"] == "priority_collision":
                for rule in conflict["rules"]:
                    to_insert.append(ConflictedRule(
                        name=rule["name"],
                        description=conflict["description"],
                        group=conflict["group"],
                        priority=conflict["priority"],
                        enabled=rule.get("enabled", True),
                        condition_dsl=json.dumps(rule["condition_dsl"]),
                        action=rule.get("action", ""),
                        rule_metadata=None,
                        conflict_type=conflict["type"],
                        conflict_description=conflict["description"],
                        conflicting_rule_id=None,
                        conflicting_rule_name=None,
                        status="detected"
                    ))
        if to_insert:
            db.bulk_save_objects(to_insert)
            db.commit()
    except Exception as e:
        db.rollback()
        return JSONResponse(status_code=500, content={"detail": f"Failed to persist detected conflicts: {str(e)}"})
    return result


# ── Parked Conflict Rules ──────────────────────────────────────────

@router.get("/conflicts/parked")
def list_parked_conflicts(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, dismissed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all rules that were rejected due to conflicts and parked for review."""
    query = db.query(ConflictedRule)
    if status:
        query = query.filter(ConflictedRule.status == status)
    parked = query.order_by(ConflictedRule.submitted_at.desc()).all()
    results = []
    for p in parked:
        results.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "group": p.group,
            "priority": p.priority,
            "enabled": p.enabled,
            "condition_dsl": json.loads(p.condition_dsl) if p.condition_dsl else None,
            "action": p.action,
            "conflict_type": p.conflict_type,
            "conflict_description": p.conflict_description,
            "conflicting_rule_id": p.conflicting_rule_id,
            "conflicting_rule_name": p.conflicting_rule_name,
            "submitted_by": p.submitted_by,
            "submitted_at": p.submitted_at.isoformat() if p.submitted_at else None,
            "status": p.status,
            "reviewed_by": p.reviewed_by,
            "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
            "review_notes": p.review_notes,
        })
    return results


@router.put("/conflicts/parked/{parked_id}")
def review_parked_conflict(
    parked_id: int,
    action: str = Query(..., description="Action: 'dismiss' or 'resolve_create'"),
    notes: Optional[str] = Query(None, description="Review notes"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Review a parked conflict rule.
    - 'dismiss': Mark as dismissed (business user decided not to create it).
    - 'resolve_create': Only allowed via POST with a modified rule body (see resolve endpoint below).
    """
    from datetime import datetime

    parked = db.query(ConflictedRule).filter(ConflictedRule.id == parked_id).first()
    if not parked:
        raise HTTPException(status_code=404, detail="Parked conflict rule not found")

    if action == "dismiss":
        parked.status = "dismissed"
        parked.reviewed_by = current_user.id
        parked.reviewed_at = datetime.utcnow()
        parked.review_notes = notes
        db.commit()
        return {"message": f"Parked rule '{parked.name}' dismissed.", "status": "dismissed"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'dismiss'. To create, use the resolve endpoint with modifications.")


@router.post("/conflicts/parked/{parked_id}/resolve")
def resolve_parked_conflict(
    parked_id: int,
    modified_rule: RuleCreate,
    notes: Optional[str] = Query(None, description="Review notes"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Resolve a parked conflict by submitting a modified version of the rule.
    The rule must be changed from the original parked version — unchanged rules are rejected.
    The modified rule goes through normal conflict checking.
    """
    from datetime import datetime
    import hashlib

    parked = db.query(ConflictedRule).filter(ConflictedRule.id == parked_id).first()
    if not parked:
        raise HTTPException(status_code=404, detail="Parked conflict rule not found")

    if parked.status != "pending":
        raise HTTPException(status_code=400, detail=f"This parked rule is already '{parked.status}'. Only 'pending' rules can be resolved.")

    # Check if the user actually modified the rule
    original_condition = json.loads(parked.condition_dsl) if isinstance(parked.condition_dsl, str) else parked.condition_dsl
    modified_condition = modified_rule.condition_dsl if isinstance(modified_rule.condition_dsl, dict) else json.loads(modified_rule.condition_dsl)

    original_hash = hashlib.md5(json.dumps({
        "name": parked.name,
        "group": parked.group,
        "priority": parked.priority,
        "condition_dsl": json.dumps(original_condition, sort_keys=True),
        "action": parked.action,
    }, sort_keys=True).encode()).hexdigest()

    modified_hash = hashlib.md5(json.dumps({
        "name": modified_rule.name,
        "group": modified_rule.group,
        "priority": modified_rule.priority,
        "condition_dsl": json.dumps(modified_condition, sort_keys=True),
        "action": modified_rule.action,
    }, sort_keys=True).encode()).hexdigest()

    if original_hash == modified_hash:
        raise HTTPException(
            status_code=400,
            detail="The rule has not been modified. Please change the priority, condition, group, or action to resolve the conflict before creating."
        )

    # Try to create the modified rule — use the FULL BRMS validation
    # (same as create/update) so that brms_overlap is properly caught.
    validation_result = RuleValidationService(db).validate(modified_rule.model_dump())
    potential_conflicts = validation_result.get("conflicts", [])

    BLOCKING_CONFLICT_TYPES = {"priority_collision", "duplicate_condition", "brms_dead_rule", "brms_overlap"}
    blocking_conflicts = [
        c for c in potential_conflicts
        if c.get("type") in BLOCKING_CONFLICT_TYPES
        and (c.get("existing_rule_id") is not None or c.get("type") == "brms_dead_rule")
    ]

    if blocking_conflicts:
        # Still conflicts — update parked entry with the new version and new conflict info
        parked.name = modified_rule.name
        parked.description = modified_rule.description
        parked.group = modified_rule.group
        parked.priority = modified_rule.priority
        parked.enabled = modified_rule.enabled
        parked.condition_dsl = json.dumps(modified_condition)
        parked.action = modified_rule.action
        parked.rule_metadata = json.dumps(modified_rule.rule_metadata) if modified_rule.rule_metadata else None
        parked.conflict_type = blocking_conflicts[0].get("type", "unknown")
        parked.conflict_description = blocking_conflicts[0].get("description", "")
        parked.conflicting_rule_id = blocking_conflicts[0].get("existing_rule_id")
        parked.conflicting_rule_name = blocking_conflicts[0].get("existing_rule_name")
        db.commit()

        raise HTTPException(
            status_code=400,
            detail={
                "message": "The modified rule still has conflicts. Please make further changes.",
                "conflicts": blocking_conflicts
            }
        )

    # No conflicts — create the rule
    service = RuleService(db)
    created_rule = service.create_rule(modified_rule, current_user.id)
    # invalidate_conflict_cache()

    # Mark parked rule as approved
    parked.status = "approved"
    parked.reviewed_by = current_user.id
    parked.reviewed_at = datetime.utcnow()
    parked.review_notes = notes or "Resolved with modifications"
    db.commit()

    return {
        "message": f"Rule '{modified_rule.name}' created successfully after resolving conflicts.",
        "status": "approved",
        "created_rule": serialize_rule(created_rule)
    }



@router.delete("/conflicts/parked/{parked_id}")
def delete_parked_conflict(
    parked_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Permanently delete a parked conflict rule."""
    parked = db.query(ConflictedRule).filter(ConflictedRule.id == parked_id).first()
    if not parked:
        raise HTTPException(status_code=404, detail="Parked conflict rule not found")
    name = parked.name
    db.delete(parked)
    db.commit()
    return {"message": f"Parked rule '{name}' deleted.", "id": parked_id}


@router.post("/bulk/async")
def async_bulk_create_rules(
    rules: List[RuleCreate],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit a bulk rule creation job that runs validation asynchronously.

    Returns a job_id immediately.  Poll ``/rules/bulk/async/{job_id}`` for status.
    """
    from app.workers.validation_worker import submit_bulk_validation
    from app.config import settings

    payloads = [r.model_dump() for r in rules]
    db_url = str(settings.DATABASE_URL)
    job_id = submit_bulk_validation(payloads, current_user.id, db_url)
    return {"job_id": job_id, "total_rules": len(rules), "status": "submitted"}


@router.get("/bulk/async/{job_id}")
def get_async_bulk_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the status of an async bulk creation job."""
    from app.workers.validation_worker import get_job_status

    status = get_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@router.get("/bulk/async")
def list_async_bulk_jobs(
    current_user: User = Depends(get_current_user),
):
    """List recent async bulk validation jobs."""
    from app.workers.validation_worker import list_jobs
    return list_jobs()


def invalidate_conflict_cache(db: Session):
    engine = ReteEngine(db)
    if engine._optimized_engine:
        engine._optimized_engine.invalidate_cache()
    engine.reload_rules()
    # Also invalidate compiled rule + index cache
    try:
        from app.validation._compiled_cache import invalidate as invalidate_compiled_cache
        invalidate_compiled_cache()
    except ImportError:
        pass