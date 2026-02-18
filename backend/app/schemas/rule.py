from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class ConditionNode(BaseModel):
    type: str
    op: Optional[str] = None
    field: Optional[str] = None
    value: Optional[Any] = None
    children: Optional[List['ConditionNode']] = None

class RuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    group: Optional[str] = None
    priority: int = 0
    enabled: bool = True
    condition_dsl: Dict[str, Any]
    action: str
    rule_metadata: Optional[Dict[str, Any]] = None

class RuleCreate(RuleBase):
    pass

class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    group: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None
    condition_dsl: Optional[Dict[str, Any]] = None
    action: Optional[str] = None
    rule_metadata: Optional[Dict[str, Any]] = None

class RuleResponse(RuleBase):
    id: int
    current_version: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    
    class Config:
        from_attributes = True

class RuleVersionResponse(BaseModel):
    id: int
    rule_id: int
    version: int
    name: str
    description: Optional[str] = None
    group: Optional[str] = None
    priority: int
    enabled: bool
    condition_dsl: Dict[str, Any]
    action: str
    rule_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    created_by: Optional[int] = None
    
    class Config:
        from_attributes = True

class SimulateRequest(BaseModel):
    event: Dict[str, Any]
    rule_ids: Optional[List[int]] = None

class SimulateResponse(BaseModel):
    matched_rules: List[Dict[str, Any]]
    execution_order: List[int]
    explanations: Dict[int, str]
    dry_run: bool = True

class DependencyGraph(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]

class ConflictReport(BaseModel):
    conflicts: List[Dict[str, Any]]
