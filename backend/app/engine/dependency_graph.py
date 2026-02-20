from sqlalchemy.orm import Session
from app.models.rule import Rule
from typing import Dict, Any, List, Set
import json

class DependencyGraphBuilder:
    def __init__(self, db: Session):
        self.db = db
    
    def _parse_condition(self, condition_dsl) -> Dict[str, Any]:
        """Parse condition_dsl whether it's a string or dict."""
        if isinstance(condition_dsl, str):
            return json.loads(condition_dsl)
        return condition_dsl
    
    def build_graph(self) -> Dict[str, Any]:
        rules = self.db.query(Rule).filter(Rule.enabled == True).all()
        
        nodes = []
        edges = []
        
        for rule in rules:
            nodes.append({
                "id": rule.id,
                "name": rule.name,
                "group": rule.group,
                "priority": rule.priority
            })
        
        for i, rule1 in enumerate(rules):
            fields1 = self._extract_fields(self._parse_condition(rule1.condition_dsl))
            
            for rule2 in rules[i+1:]:
                fields2 = self._extract_fields(self._parse_condition(rule2.condition_dsl))
                
                shared_fields = fields1 & fields2
                if shared_fields:
                    edges.append({
                        "source": rule1.id,
                        "target": rule2.id,
                        "shared_fields": list(shared_fields)
                    })
        
        return {
            "nodes": nodes,
            "edges": edges
        }
    
    def _extract_fields(self, condition: Dict[str, Any]) -> Set[str]:
        fields = set()
        
        if not condition:
            return fields
        
        if condition.get("type") == "condition":
            if condition.get("field"):
                fields.add(condition["field"])
        elif condition.get("type") == "group":
            for child in condition.get("children", []):
                fields.update(self._extract_fields(child))
        
        return fields