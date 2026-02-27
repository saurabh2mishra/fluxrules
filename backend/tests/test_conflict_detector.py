from app.services.conflict_detector import ConflictDetector


class DummyDB:
    def __init__(self, rules):
        self._rules = rules
    def query(self, model):
        class Query:
            def __init__(self, rules):
                self._rules = rules
            def filter(self, *args, **kwargs):
                return self
            def order_by(self, *args, **kwargs):
                return self
            def all(self):
                return self._rules
        return Query(self._rules)

def make_rule(id, name, group, priority, condition_dsl):
    class RuleObj:
        def __init__(self, id, name, group, priority, condition_dsl):
            self.id = id
            self.name = name
            self.group = group
            self.priority = priority
            self.condition_dsl = condition_dsl
            self.enabled = True
            self.action = "do_something"
    return RuleObj(id, name, group, priority, condition_dsl)

def test_detect_duplicate_conditions():
    rules = [
        make_rule(1, "Rule1", "group1", 10, {"type": "condition", "field": "amount", "op": ">", "value": 100}),
        make_rule(2, "Rule2", "group1", 20, {"type": "condition", "field": "amount", "op": ">", "value": 100}),
    ]
    db = DummyDB(rules)
    detector = ConflictDetector(db)
    conflicts = detector.detect_all_conflicts()["conflicts"]
    assert any(c["type"] == "duplicate_condition" for c in conflicts)

def test_detect_priority_collisions():
    rules = [
        make_rule(1, "Rule1", "group1", 10, {"type": "condition", "field": "amount", "op": ">", "value": 100}),
        make_rule(2, "Rule2", "group1", 10, {"type": "condition", "field": "amount", "op": "<", "value": 200}),
    ]
    db = DummyDB(rules)
    detector = ConflictDetector(db)
    conflicts = detector.detect_all_conflicts()["conflicts"]
    assert any(c["type"] == "priority_collision" for c in conflicts)