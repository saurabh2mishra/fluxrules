from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.models.rule import Rule, RuleVersion
from app.schemas.rule import RuleCreate, RuleUpdate
from app.services.audit_service import AuditService
import json

class RuleService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
    
    def list_rules(
        self,
        skip: int = 0,
        limit: int = 100,
        group: Optional[str] = None,
        enabled: Optional[bool] = None
    ) -> List[Rule]:
        query = self.db.query(Rule)
        if group:
            query = query.filter(Rule.group == group)
        if enabled is not None:
            query = query.filter(Rule.enabled == enabled)
        return query.offset(skip).limit(limit).all()
    
    def get_rule(self, rule_id: int) -> Optional[Rule]:
        return self.db.query(Rule).filter(Rule.id == rule_id).first()
    
    def create_rule(self, rule_data: RuleCreate, user_id: int) -> Rule:
        rule = Rule(
            name=rule_data.name,
            description=rule_data.description,
            group=rule_data.group,
            priority=rule_data.priority,
            enabled=rule_data.enabled,
            condition_dsl=json.dumps(rule_data.condition_dsl),
            action=rule_data.action,
            rule_metadata=json.dumps(rule_data.rule_metadata) if rule_data.rule_metadata else None,
            created_by=user_id,
            current_version=1
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        
        self._create_version(rule, user_id)
        self.audit_service.log_action("create", "rule", rule.id, user_id, "Rule created")
        
        return rule
    
    def update_rule(self, rule_id: int, rule_data: RuleUpdate, user_id: int) -> Optional[Rule]:
        rule = self.get_rule(rule_id)
        if not rule:
            return None
        
        update_data = rule_data.dict(exclude_unset=True)
        if "condition_dsl" in update_data:
            update_data["condition_dsl"] = json.dumps(update_data["condition_dsl"])
        if "rule_metadata" in update_data:
            update_data["rule_metadata"] = json.dumps(update_data["rule_metadata"])
        
        for field, value in update_data.items():
            setattr(rule, field, value)
        
        rule.current_version += 1
        self.db.commit()
        self.db.refresh(rule)
        
        self._create_version(rule, user_id)
        self.audit_service.log_action("update", "rule", rule.id, user_id, "Rule updated")
        
        return rule
    
    def delete_rule(self, rule_id: int) -> bool:
        rule = self.get_rule(rule_id)
        if not rule:
            return False
        self.db.delete(rule)
        self.db.commit()
        self.audit_service.log_action("delete", "rule", rule_id, None, "Rule deleted")
        return True
    
    def _create_version(self, rule: Rule, user_id: int):
        version = RuleVersion(
            rule_id=rule.id,
            version=rule.current_version,
            name=rule.name,
            description=rule.description,
            group=rule.group,
            priority=rule.priority,
            enabled=rule.enabled,
            condition_dsl=rule.condition_dsl,
            action=rule.action,
            rule_metadata=rule.rule_metadata,
            created_by=user_id
        )
        self.db.add(version)
        self.db.commit()
    
    def get_rule_versions(self, rule_id: int) -> List[RuleVersion]:
        return self.db.query(RuleVersion).filter(
            RuleVersion.rule_id == rule_id
        ).order_by(RuleVersion.version.desc()).all()
    
    def get_rule_version(self, rule_id: int, version: int) -> Optional[RuleVersion]:
        return self.db.query(RuleVersion).filter(
            RuleVersion.rule_id == rule_id,
            RuleVersion.version == version
        ).first()
    
    def get_version_diff(self, rule_id: int, version1: int, version2: int) -> Optional[Dict[str, Any]]:
        v1 = self.get_rule_version(rule_id, version1)
        v2 = self.get_rule_version(rule_id, version2)
        
        if not v1 or not v2:
            return None
        
        diff = {}
        fields = ["name", "description", "group", "priority", "enabled", "condition_dsl", "action", "rule_metadata"]
        
        for field in fields:
            val1 = getattr(v1, field)
            val2 = getattr(v2, field)
            if val1 != val2:
                diff[field] = {"version1": val1, "version2": val2}
        
        return {
            "rule_id": rule_id,
            "version1": version1,
            "version2": version2,
            "differences": diff
        }