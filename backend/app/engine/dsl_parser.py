from typing import Dict, Any

class DSLParser:
    def parse(self, dsl: Dict[str, Any]) -> str:
        return self._parse_node(dsl)
    
    def _parse_node(self, node: Dict[str, Any]) -> str:
        if node["type"] == "condition":
            return self._parse_condition(node)
        elif node["type"] == "group":
            return self._parse_group(node)
        return ""
    
    def _parse_condition(self, node: Dict[str, Any]) -> str:
        field = node["field"]
        op = node["op"]
        value = node["value"]
        
        op_map = {
            ">": "m.{} > {}",
            ">=": "m.{} >= {}",
            "<": "m.{} < {}",
            "<=": "m.{} <= {}",
            "==": "m.{} == {}",
            "!=": "m.{} != {}",
        }
        
        template = op_map.get(op, "m.{} == {}")
        return template.format(field, repr(value))
    
    def _parse_group(self, node: Dict[str, Any]) -> str:
        op = node["op"]
        children = node.get("children", [])
        
        parsed_children = [self._parse_node(child) for child in children]
        
        if op == "AND":
            return " & ".join(f"({c})" for c in parsed_children)
        elif op == "OR":
            return " | ".join(f"({c})" for c in parsed_children)
        
        return ""