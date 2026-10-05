"""DSL parser tests """

from fluxrules.domain.dsl.expression_parser import DSLParser


def test_parse_simple_condition():
    parser = DSLParser()
    result = parser.parse({"type": "condition", "field": "amount", "op": ">", "value": 100})
    assert "amount" in result
    assert "100" in result


def test_parse_and_group():
    parser = DSLParser()
    result = parser.parse(
        {
            "type": "group",
            "op": "AND",
            "children": [
                {"type": "condition", "field": "amount", "op": ">", "value": 100},
                {"type": "condition", "field": "status", "op": "==", "value": "active"},
            ],
        }
    )
    assert "amount" in result
    assert "status" in result


def test_parse_nested_groups():
    parser = DSLParser()
    result = parser.parse(
        {
            "type": "group",
            "op": "OR",
            "children": [
                {
                    "type": "group",
                    "op": "AND",
                    "children": [
                        {"type": "condition", "field": "a", "op": ">", "value": 1},
                        {"type": "condition", "field": "b", "op": "<", "value": 10},
                    ],
                },
                {"type": "condition", "field": "c", "op": "==", "value": "test"},
            ],
        }
    )
    assert "a" in result or "b" in result  # parser should include field names
