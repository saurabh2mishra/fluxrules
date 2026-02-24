from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..deps import get_db
from ...models.rule import Rule
from ...models.user import User
import json

router = APIRouter()

@router.get("/rules/graph/dependencies")
def get_rule_dependency_graph(db: Session = Depends(get_db)):
    # Fetch all rules
    rules = db.query(Rule).all()
    nodes = []
    edges = []
    rule_fields = {}
    for rule in rules:
        # Extract fields from condition_dsl JSON
        fields = set()
        dsl = rule.condition_dsl
        if isinstance(dsl, dict):
            # Recursively extract field names
            def extract_fields(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k == 'field':
                            fields.add(v)
                        else:
                            extract_fields(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_fields(item)
            extract_fields(dsl)
        rule_fields[rule.id] = list(fields)
        nodes.append({
            "id": rule.id,
            "name": rule.name,
            "priority": getattr(rule, 'priority', None),
            "fields": list(fields)
        })
    # Build edges: connect rules sharing at least one field
    for i, rule_a in enumerate(rules):
        for j, rule_b in enumerate(rules):
            if i >= j:
                continue
            shared = set(rule_fields[rule_a.id]) & set(rule_fields[rule_b.id])
            for field in shared:
                edges.append({
                    "source": rule_a.id,
                    "target": rule_b.id,
                    "shared_field": field,
                    "label": field
                })
    return {"nodes": nodes, "edges": edges}
