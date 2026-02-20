from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
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
from app.engine.dependency_graph import DependencyGraphBuilder
# Use optimized conflict detector for better performance
try:
    from app.services.optimized_conflict_detector import OptimizedConflictDetector as ConflictDetector, invalidate_conflict_cache
except ImportError:
    from app.services.conflict_detector import ConflictDetector
    def invalidate_conflict_cache():
        pass
from app.engine.actions import get_available_actions, execute_action

router = APIRouter(prefix="/rules", tags=["rules"])

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
    rule: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Validate a rule before saving - check for conflicts and similar rules"""
    detector = ConflictDetector(db)
    conflicts = detector.check_new_rule_conflicts(rule)
    
    # Find similar rules (same group or similar conditions)
    similar_rules = []
    existing_rules = db.query(Rule).filter(Rule.enabled == True).all()
    
    for existing in existing_rules:
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
                reasons.append(f"Similar name")
        
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
    
    return {
        "valid": len(conflicts) == 0,
        "conflicts": conflicts,
        "similar_rules": similar_rules[:5],  # Top 5 similar rules
        "message": "No conflicts found. Rule is ready to save." if len(conflicts) == 0 else "Conflicts detected. Please review before saving."
    }

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
def create_rule(
    rule: RuleCreate,
    skip_conflict_check: bool = Query(False, description="Skip conflict checking for faster creation"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check for conflicts BEFORE creating (unless skipped for bulk operations)
    if not skip_conflict_check:
        detector = ConflictDetector(db)
        potential_conflicts = detector.check_new_rule_conflicts(rule)
        
        if potential_conflicts:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Rule conflicts detected. Please resolve before creating.",
                    "conflicts": potential_conflicts
                }
            )
    
    # Invalidate conflict cache after creating
    invalidate_conflict_cache()
    
    service = RuleService(db)
    created_rule = service.create_rule(rule, current_user.id)
    return serialize_rule(created_rule)


@router.post("/bulk", response_model=List[RuleResponse])
def bulk_create_rules(
    rules: List[RuleCreate],
    validate_conflicts: bool = Query(True, description="Check all conflicts at the end"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create multiple rules in a single request.
    Much faster than creating rules one by one.
    """
    service = RuleService(db)
    created_rules = []
    errors = []
    
    for i, rule in enumerate(rules):
        try:
            created_rule = service.create_rule(rule, current_user.id)
            created_rules.append(serialize_rule(created_rule))
        except Exception as e:
            errors.append({"index": i, "rule_name": rule.name, "error": str(e)})
    
    # Invalidate cache after bulk operation
    invalidate_conflict_cache()
    
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
    current_user: User = Depends(get_current_user)
):
    # Check for conflicts BEFORE updating
    detector = ConflictDetector(db)
    potential_conflicts = detector.check_update_rule_conflicts(rule_id, rule_update)
    
    if potential_conflicts:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Rule conflicts detected. Please resolve before updating.",
                "conflicts": potential_conflicts
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

@router.get("/graph/dependencies", response_model=DependencyGraph)
def get_dependency_graph(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    builder = DependencyGraphBuilder(db)
    return builder.build_graph()

@router.get("/conflicts/detect", response_model=ConflictReport)
def detect_conflicts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    detector = ConflictDetector(db)
    return detector.detect_all_conflicts()