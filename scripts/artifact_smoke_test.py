"""Smoke test run against an installed fluxrules artifact.

Called by CI after pip-installing each sdist/wheel into a clean venv.
Exits non-zero on any assertion failure.
"""

import importlib.resources

from fluxrules import PhreakEngine, Rule, RuleBuilder, __version__, evaluate

rule = Rule(
    name="adult",
    condition_dsl={"type": "condition", "field": "age", "op": ">=", "value": 18},
    action="allow",
)
result = evaluate(rule, {"age": 30})
assert result.fired_rules == [rule.id], result.fired_rules
assert result.actions == ["allow"], result.actions

built = (
    RuleBuilder()
    .name("adult_built")
    .condition({"type": "condition", "field": "age", "op": ">=", "value": 18})
    .action("allow")
    .build()
)
assert isinstance(built, Rule), type(built)
assert evaluate([rule, built], {"age": 30}).actions == ["allow", "allow"]

engine = PhreakEngine()
engine.load_rules([rule])
assert engine.evaluate({"age": 30}).fired_rules == [rule.id]

assert importlib.resources.files("fluxrules").joinpath("py.typed").is_file()

print(f"SMOKE PASS: fluxrules {__version__} -> {result.actions}")
