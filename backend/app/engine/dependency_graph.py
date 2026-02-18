from sqlalchemy.orm import Session
from app.models.rule import Rule
from typing import Dict, Any, List, Set
import json

class DependencyGraphBuilder:
    def __init__(self, db: Session):
        self.db = db
    
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
            # fields1 = self._extract_fields(json.loads(rule1.condition_dsl))
            fields1 = self._extract_fields(rule1.condition_dsl)
            
            for rule2 in rules[i+1:]:
                # fields2 = self._extract_fields(json.loads(rule2.condition_dsl))
                fields2 = self._extract_fields(rule2.condition_dsl)
                
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
        
        if condition["type"] == "condition":
            fields.add(condition["field"])
        elif condition["type"] == "group":
            for child in condition.get("children", []):
                fields.update(self._extract_fields(child))
        
        return fields