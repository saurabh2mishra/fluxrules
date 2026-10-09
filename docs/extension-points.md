# Extension Points

FluxRules is extended through a small set of **registries** plus optional
**entry-point auto-discovery**. This page is the catalog and the stability
policy; the deep how-to guides live on their own pages and are linked below.

## The extension points

| What you add | Public entry point | How-to guide |
|--------------|--------------------|--------------|
| Condition operator | [`register_operator(name, func)`](reference/public-api.md) | [Conditions](conditions.md) |
| Rule engine | [`register_engine(name, cls)`](reference/public-api.md) | [Custom Engines](custom-engines.md) |
| Action | [`action_registry.register(...)`](action-registry.md) | [Custom Actions](custom-actions.md) |
| Pipeline transform | [`pipeline.registry.register(cls)`](fact-pipeline.md) | [Custom Transforms](custom-transforms.md) |
| Validator | [`ValidationService.register_validator(...)`](validation-framework.md) | [Validation Framework](validation-framework.md) |

Each registry is a plain, importable object - there is no hidden framework. A
custom engine, for example, becomes selectable everywhere the built-in engine
is (the Python factory, the HTTP API, and the CLI `--engine` flag) the moment it
is registered:

```python
# python skip
from fluxrules import register_engine, get_engine
from fluxrules.engine.base import BaseEngine


class MyEngine(BaseEngine):
    def _evaluate_rules(self, rule_ids, facts):
        # Return (fired_rule_ids, actions, explanations)
        ...


register_engine("MYENGINE", MyEngine)
engine = get_engine("MYENGINE")  # now resolvable by name
```

Built-in engines (`PHREAK`) cannot be overridden or removed, so
`get_engine("PHREAK")` is always stable.

## Proving a custom engine is correct

A third-party engine can prove it matches FluxRules semantics using the public
conformance kit, which drives it against the independent, dependency-free
`ReferenceEvaluator` across a battery of rule shapes:

```python
# python skip
from fluxrules.testing import assert_engine_contract
from my_pkg import MyEngine


def test_my_engine_is_conformant():
    assert_engine_contract(MyEngine)
```

`assert_engine_contract` accepts an engine class, a zero-argument factory, or an
instance, and raises `AssertionError` naming any case where the fired-rule set
diverges from the reference. Pass `cases=` to supply your own battery.

## Entry-point auto-discovery

Packages can advertise extensions so they register automatically, without the
host application importing them by hand. Declare entry points in the plugin
package's `pyproject.toml`:

```toml
[project.entry-points."fluxrules.operators"]
within_range = "my_pkg.operators:within_range"

[project.entry-points."fluxrules.engines"]
myengine = "my_pkg.engine:MyEngine"

[project.entry-points."fluxrules.actions"]
slack_notify = "my_pkg.actions:slack_notify"

[project.entry-points."fluxrules.transforms"]
redact = "my_pkg.transforms:Redact"
```

Then, once, at application startup:

```python
# python skip
from fluxrules.plugins.discovery import load_plugins

loaded = load_plugins()  # {"fluxrules.operators": ["within_range"], ...}
```

Discovery is **explicit** - it is never an import side effect - so applications
stay in control of when third-party code is loaded. A plugin that fails to load
is logged and skipped rather than aborting discovery.

## Stability policy

Extension points follow the project's semantic-versioning contract for the
`0.x` line:

- **Registry signatures** (`register_operator`, `register_engine`,
  `register_validator`, the action and transform registries) and the
  **entry-point group names** (`fluxrules.operators`, `fluxrules.engines`,
  `fluxrules.actions`, `fluxrules.transforms`) are treated as public API. A
  breaking change to any of them is called out in [the changelog](changelog.md)
  under a `Changed` or `Removed` heading and accompanies a minor version bump
  while `0.x`.
- **`BaseEngine`** is the supported base class for custom engines. New
  *optional* hooks may be added in minor releases; the required
  `_evaluate_rules` contract is covered by `assert_engine_contract`, so a
  conformant engine keeps working across minor upgrades.
- **The conformance battery** may gain cases in minor releases (a stricter
  oracle), but existing correct engines are expected to keep passing. If a case
  is tightened in a way that could fail a previously-conformant engine, it is
  documented as a `Changed` entry.

See [Contributing](contributing.md) to propose a new extension point.
