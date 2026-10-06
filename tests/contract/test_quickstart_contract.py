"""The getting-started contract: a working rule in ten lines, no setup.

This is the first thing anyone runs, and the thing most easily broken by a
refactor that looks harmless from inside the library. Every assertion here
corresponds to a promise the README makes on the first screen:

* ``from fluxrules import Rule, evaluate`` is enough - no reaching into
  ``fluxrules.domain`` or ``fluxrules.engine.phreak``.
* Constructing a ``Rule`` touches no database, so importing a module that
  defines rules cannot open a connection or create a file.
* ``evaluate`` takes the rule itself. No ``Ruleset``, no ``to_engine_rule()``.
* The answer is on ``fired_rules``, under that name, on every path.

CI runs this file on its own, before the rest of the suite, so a broken
first-run experience fails loudly rather than hiding among 1,700 passing tests.
"""

from __future__ import annotations

import subprocess
import sys
from textwrap import dedent

#: The literal README quickstart. Ten lines, counted.
QUICKSTART = dedent(
    """
    from fluxrules import Rule, evaluate

    rule = Rule(
        name="high_value_transaction",
        condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 5000},
        action="manual_review",
    )

    result = evaluate(rule, {"amount": 6000})
    print(result.fired_rules, result.actions)
    """
).strip()


def test_quickstart_is_ten_lines_or_fewer() -> None:
    """If the happy path needs more than ten lines, the API regressed."""
    assert len([ln for ln in QUICKSTART.splitlines() if ln.strip()]) <= 10


def test_quickstart_runs_in_a_clean_interpreter(tmp_path) -> None:
    """Run it as a fresh process in an empty cwd, like a new user would.

    A subprocess is the point: it catches import-time side effects and any
    state this test session has already warmed up. The empty cwd catches a
    regression where merely constructing a ``Rule`` creates a database file.
    """
    script = tmp_path / "quickstart.py"
    script.write_text(QUICKSTART, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        timeout=120,
    )

    assert completed.returncode == 0, (
        f"The documented quickstart failed.\nstdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}"
    )
    assert "manual_review" in completed.stdout

    # Constructing and evaluating a rule must not write anything to disk.
    leftovers = sorted(p.name for p in tmp_path.iterdir() if p.name != "quickstart.py")
    assert leftovers == [], f"The quickstart created files on disk: {leftovers}"


def test_quickstart_needs_no_warnings_to_be_silenced() -> None:
    """The first-run path must be clean, not merely functional."""
    import warnings

    from fluxrules import Rule, evaluate

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        rule = Rule(
            name="high_value_transaction",
            condition_dsl={
                "type": "condition",
                "field": "amount",
                "op": ">",
                "value": 5000,
            },
            action="manual_review",
        )
        result = evaluate(rule, {"amount": 6000})

    assert result.fired_rules == [rule.id]
    assert result.actions == ["manual_review"]


def test_the_answer_is_always_called_fired_rules() -> None:
    """One name for "what matched", on every entry point."""
    from fluxrules import PhreakEngine, Rule, RuleBuilder, evaluate

    dsl = {"type": "condition", "field": "amount", "op": ">", "value": 5000}
    rule = Rule(name="r", condition_dsl=dsl, action="manual_review")
    built = RuleBuilder().name("b").condition(dsl).action("manual_review").build()

    engine = PhreakEngine()
    engine.load_rules([rule])

    results = [
        evaluate(rule, {"amount": 6000}),
        evaluate([rule], {"amount": 6000}),
        evaluate(built, {"amount": 6000}),
        engine.evaluate({"amount": 6000}),
    ]

    for result in results:
        assert result.fired_rules, "every path reports matches on .fired_rules"
        assert result.actions == ["manual_review"]
        assert not hasattr(result, "matched_rule_ids")


def test_built_and_constructed_rules_get_distinct_ids() -> None:
    """Mixing the two authoring paths must not collide on auto-assigned IDs.

    ``Rule`` draws auto IDs from a module-level generator while ``RuleBuilder``
    used to allocate from a fresh one of its own. Both sequential generators
    start at 1, so the first built rule and the first constructed rule were
    handed the same ID - and evaluating them together failed validation with
    "Ruleset has duplicate rule ids". The builder now defers to ``Rule``.
    """
    from fluxrules import Rule, RuleBuilder, evaluate

    dsl = {"type": "condition", "field": "age", "op": ">=", "value": 18}
    constructed = Rule(name="constructed", condition_dsl=dsl, action="allow")
    built = RuleBuilder().name("built").condition(dsl).action("allow").build()

    assert constructed.id != built.id

    result = evaluate([constructed, built], {"age": 30})
    assert sorted(result.fired_rules) == sorted([constructed.id, built.id])
    assert result.actions == ["allow", "allow"]
