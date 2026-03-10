from collections import defaultdict
from itertools import combinations
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ...models.rule import Rule
from ...models.user import User

router = APIRouter(tags=["dependency-graph"])


def _extract_fields(condition_dsl) -> Set[str]:
    fields: Set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("field"):
                fields.add(str(node["field"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(condition_dsl)
    return fields


def _load_rules(db: Session) -> List[Dict]:
    rules = db.query(Rule).filter(Rule.enabled.is_(True)).all()
    out = []
    for rule in rules:
        out.append(
            {
                "id": rule.id,
                "name": rule.name,
                "group": rule.group,
                "priority": rule.priority,
                "fields": sorted(list(_extract_fields(rule.condition_dsl))),
            }
        )
    return out


def _apply_filters(rules: List[Dict], group: Optional[str], field: Optional[str], rule_name: Optional[str]) -> List[Dict]:
    filtered = rules
    if group:
        filtered = [r for r in filtered if (r.get("group") or "") == group]
    if field:
        filtered = [r for r in filtered if field in r.get("fields", [])]
    if rule_name:
        n = rule_name.lower()
        filtered = [r for r in filtered if n in r.get("name", "").lower()]
    return filtered


def _build_relationships(rules: List[Dict]):
    field_to_rule_ids = defaultdict(list)
    rule_by_id = {r["id"]: r for r in rules}

    for rule in rules:
        for f in rule["fields"]:
            field_to_rule_ids[f].append(rule["id"])

    pair_to_fields = defaultdict(set)
    per_rule_connections = defaultdict(set)
    for field, ids in field_to_rule_ids.items():
        unique_ids = sorted(set(ids))
        for left, right in combinations(unique_ids, 2):
            pair_to_fields[(left, right)].add(field)
            per_rule_connections[left].add(right)
            per_rule_connections[right].add(left)

    return field_to_rule_ids, pair_to_fields, per_rule_connections, rule_by_id


@router.get("/rules/graph/summary")
def get_dependency_summary(
    group: Optional[str] = Query(None),
    field: Optional[str] = Query(None),
    rule_name: Optional[str] = Query(None),
    limit: int = Query(20, ge=5, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rules = _load_rules(db)
    filtered = _apply_filters(rules, group=group, field=field, rule_name=rule_name)

    field_to_rule_ids, pair_to_fields, per_rule_connections, rule_by_id = _build_relationships(filtered)

    top_shared_fields = []
    for shared_field, ids in field_to_rule_ids.items():
        count = len(set(ids))
        if count < 2:
            continue
        top_shared_fields.append(
            {
                "field": shared_field,
                "rule_count": count,
                "pair_count": (count * (count - 1)) // 2,
            }
        )
    top_shared_fields.sort(key=lambda x: (x["pair_count"], x["rule_count"]), reverse=True)

    connected_rows = []
    isolated_rows = []
    for rid, rule in rule_by_id.items():
        connections = len(per_rule_connections.get(rid, set()))
        row = {
            "id": rid,
            "name": rule["name"],
            "group": rule.get("group"),
            "connections": connections,
            "field_count": len(rule.get("fields", [])),
        }
        if connections == 0:
            isolated_rows.append(row)
        else:
            connected_rows.append(row)

    connected_rows.sort(key=lambda x: (x["connections"], x["field_count"]), reverse=True)
    isolated_rows.sort(key=lambda x: x["name"])

    return {
        "filters": {"group": group, "field": field, "rule_name": rule_name},
        "total_rules": len(rules),
        "filtered_rules": len(filtered),
        "pair_count": len(pair_to_fields),
        "available_groups": sorted(list({r.get("group") for r in rules if r.get("group")})),
        "top_shared_fields": top_shared_fields[:limit],
        "most_connected_rules": connected_rows[:limit],
        "isolated_rules": isolated_rows[:limit],
    }


@router.get("/rules/graph/dependencies")
def get_rule_dependency_graph(
    group: Optional[str] = Query(None),
    field: Optional[str] = Query(None),
    rule_name: Optional[str] = Query(None),
    max_nodes: int = Query(150, ge=50, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rules = _load_rules(db)
    filtered = _apply_filters(rules, group=group, field=field, rule_name=rule_name)

    has_filters = any([group, field, rule_name])
    if len(filtered) > max_nodes and not has_filters:
        return {
            "summary_only": True,
            "message": f"Graph details are disabled by default for {len(filtered)} rules. Apply filters to inspect relationships.",
            "nodes": [],
            "edges": [],
            "filtered_rules": len(filtered),
            "max_nodes": max_nodes,
        }

    if len(filtered) > max_nodes:
        filtered = filtered[:max_nodes]

    _, pair_to_fields, _, _ = _build_relationships(filtered)

    edges = []
    for (left, right), fields in pair_to_fields.items():
        edges.append(
            {
                "source": left,
                "target": right,
                "shared_fields": sorted(list(fields)),
                "weight": len(fields),
                "label": ", ".join(sorted(list(fields))[:2]),
            }
        )

    nodes = [
        {
            "id": r["id"],
            "name": r["name"],
            "group": r.get("group"),
            "priority": r.get("priority"),
            "fields": r.get("fields", []),
        }
        for r in filtered
    ]

    return {
        "summary_only": False,
        "message": None,
        "nodes": nodes,
        "edges": edges,
        "filtered_rules": len(nodes),
        "max_nodes": max_nodes,
    }
