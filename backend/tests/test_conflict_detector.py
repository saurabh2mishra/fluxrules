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