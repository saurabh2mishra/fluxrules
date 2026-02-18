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
from app.services.conflict_detector import ConflictDetector

router = APIRouter(prefix="/rules", tags=["rules"])

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

@router.post("", response_model=RuleResponse)
def create_rule(
    rule: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check for conflicts BEFORE creating
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
    
    service = RuleService(db)
    created_rule = service.create_rule(rule, current_user.id)
    return serialize_rule(created_rule)

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
    return {"message": "Engine reloaded successfully"}

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