"""Render ``docs/comparing-values.md`` from the comparison matrix.

The page is generated, never edited by hand: ``make docs-tables`` rewrites it,
and ``tests/docs/test_comparing_values_page.py`` fails when the committed page
differs from what this module renders, so the docs cannot drift from the code.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tests.engine.comparison_matrix import (
    CONFIGS,
    FACT_VALUES,
    KNOWN,
    MISSING,
    OPERATOR_VALUES,
    Case,
    MatrixResult,
    run_matrix,
)

PAGE = Path(__file__).resolve().parents[2] / "docs" / "comparing-values.md"

SETTING_INTROS = {
    "strict_null_handling": (
        "`EngineConfig(strict_null_handling=True)` lets `== None` match a `None` "
        "value and `!= x` match it too. By default a `None` value never matches."
    ),
    "strict_type_comparison": (
        "`EngineConfig(strict_type_comparison=True)` treats values of different "
        "types as never equal, and a boolean as a different type from a number: "
        '`5 == "5"` is no match and `5 != "5"` is a match. It orders (`>`, `<` and '
        "the like) two numbers only; any other ordering cannot be made, so it is "
        "no match and is reported (see "
        "[Comparisons that cannot be made](#comparisons-that-cannot-be-made))."
    ),
    "boolean_string_coercion": (
        '`EngineConfig(boolean_string_coercion=True)` reads the strings `"true"` and '
        '`"false"` (in any case) as `True` and `False`, on both the fact side and the '
        "rule side, before any operator runs, including the text operators."
    ),
    "missing_field=unknown": (
        '`EngineConfig(missing_field="unknown")` treats a missing field as unknown '
        "rather than as a failed check, so `NOT` over it does not fire. This becomes "
        "the default in 2.0. It changes no plain comparison, only `NOT`."
    ),
    "missing_field=false": (
        '`EngineConfig(missing_field="false")` keeps the 1.x behaviour, where `NOT` '
        "over a missing field fires, and turns off the warning about it."
    ),
    "uncomparable=unknown": (
        '`EngineConfig(uncomparable="unknown")` treats a comparison that cannot be '
        "made as unknown rather than as a failed check, so a rule fires only when "
        "its condition is definitely true: `NOT` over such a comparison does not "
        "fire. It changes no plain comparison, only `NOT`."
    ),
    "uncomparable=false": (
        '`EngineConfig(uncomparable="false")` keeps the default answers and turns '
        "off the `ComparisonWarning`. The issues are still listed in the result."
    ),
}

# Settings whose answers the page shows. Under uncomparable="raise" a fact whose
# rules cannot be compared raises instead of answering, so it has its own text.
PAGE_SETTINGS = [name for name in CONFIGS if name not in ("default", "uncomparable=raise")]

ORDERING = (">", ">=", "<", "<=")


def literal(value: Any) -> str:
    """How a value is written in Python, for a table cell."""
    if value is MISSING:
        return "(missing)"
    if isinstance(value, Decimal):
        return f'`Decimal("{value}")`'
    if isinstance(value, datetime):
        return f"`datetime({value.year}, {value.month}, {value.day}, {value.hour}, {value.minute})`"
    if isinstance(value, date):
        return f"`date({value.year}, {value.month}, {value.day})`"
    if isinstance(value, float) and math.isnan(value):
        return '`float("nan")`'
    if isinstance(value, float) and math.isinf(value):
        return '`float("inf")`'
    if isinstance(value, str):
        return f'`"{value}"`'
    if isinstance(value, list):
        return "`[" + ", ".join(literal(v).strip("`") for v in value) + "]`"
    if isinstance(value, dict):
        inner = ", ".join(f'"{k}": {literal(v).strip("`")}' for k, v in value.items())
        return "`{" + inner + "}`"
    return f"`{value!r}`"


def _rule_text(case: Case) -> str:
    inner = f"{case.op} {literal(case.value).strip('`')}"
    return f"`NOT(v {inner})`" if case.wrapper == "NOT" else f"`v {inner}`"


def _yes(fired: bool) -> str:
    return "yes" if fired else "no"


def _operator_table(result: MatrixResult, op: str) -> list[str]:
    cases = [c for c in result.cases if c.op == op and c.wrapper == "plain"]
    header = "| Fact value | " + " | ".join(literal(c.value) for c in cases) + " |"
    lines = [header, "|---|" + "---|" * len(cases)]
    for label, value in FACT_VALUES.items():
        cells = [_yes(result.reference[("default", label, c.rule_id)]) for c in cases]
        lines.append(f"| {literal(value)} | " + " | ".join(cells) + " |")
    return lines


def _not_table(result: MatrixResult) -> list[str]:
    ops = ("==", "!=", ">", ">=", "<", "<=")
    cases = [
        c for c in result.cases if c.op in ops and c.value_label == "int 5" and c.wrapper == "NOT"
    ]
    lines = [
        "| Fact value | " + " | ".join(f"`NOT(v {c.op} 5)`" for c in cases) + " |",
        "|---|" + "---|" * len(cases),
    ]
    for label, value in FACT_VALUES.items():
        cells = [_yes(result.reference[("default", label, c.rule_id)]) for c in cases]
        lines.append(f"| {literal(value)} | " + " | ".join(cells) + " |")
    return lines


def _setting_changes(result: MatrixResult, setting: str) -> list[str]:
    def changed(wrapper: str) -> list[tuple[Case, str, Any]]:
        return [
            (c, label, value)
            for c in result.cases
            if c.wrapper == wrapper
            for label, value in FACT_VALUES.items()
            if result.reference[(setting, label, c.rule_id)]
            != result.reference[("default", label, c.rule_id)]
        ]

    rows = changed("plain") or changed("NOT")
    if not rows:
        return ["With the matrix's rules and facts, this setting changes no answers."]
    lines = ["| Rule | Fact value | Default | With this setting |", "|---|---|---|---|"]
    for case, label, value in rows:
        before = result.reference[("default", label, case.rule_id)]
        lines.append(
            f"| {_rule_text(case)} | {literal(value)} | {_yes(before)} | {_yes(not before)} |"
        )
    return lines


def _uncomparable_section(result: MatrixResult) -> list[str]:
    """Every kind of comparison the matrix could not make, under the default settings."""
    return [
        "## Comparisons that cannot be made",
        "",
        'Some comparisons have no answer: `"abc" > 5`, `None > 5`, '
        '`float("nan") > 5`, a `date` against a `datetime`, `contains` on a number, '
        "an invalid regex. The condition is no match, as the tables above show. When "
        "such a comparison leaves a rule undecided, the result lists it in "
        "`comparison_issues`, with the field, the operator, both types and the "
        "reason, and `EngineConfig(uncomparable=...)` chooses what else happens:",
        "",
        "| `uncomparable` | What happens |",
        "|---|---|",
        "| `None` (default) | No match, and a `ComparisonWarning` once per field, "
        "operator and pair of types. |",
        '| `"false"` | No match, with no warning. |',
        '| `"unknown"` | Unknown: a rule fires only when its condition is definitely '
        "true, so `NOT` over it does not fire. |",
        '| `"raise"` | `UncomparableValuesError`, naming the field, the operator and both types. |',
        "",
        "A comparison that decides nothing is not reported: in "
        '`(F("v") > 5) & (F("country") == "US")` with `country` set to `"DE"`, the rule '
        'is no match whatever `v` holds, so `v = "abc"` is not reported. `==` and '
        "`!=` always have an answer: different values, `None`, `NaN` and values of "
        "different types are not equal.",
        "",
        "These are every comparison in the tables above that has no answer, under "
        "the default settings:",
        "",
        "| Fact value | Cannot be ordered (`>`, `>=`, `<`, `<=`) against | Why |",
        "|---|---|---|",
        *_issue_rows(result, ordering=True),
        "",
        "| Fact value | Operator | Why |",
        "|---|---|---|",
        *_issue_rows(result, ordering=False),
        "",
    ]


def _issue_rows(result: MatrixResult, *, ordering: bool) -> list[str]:
    """One row per fact value: what it cannot be compared with, and why."""
    rows = []
    for label, value in FACT_VALUES.items():
        issues = [
            i
            for i in result.issues.get(("default", label), ())
            if (i.operator in ORDERING) is ordering
        ]
        if not issues:
            continue
        reasons = sorted({i.reason for i in issues})
        if ordering:
            what = sorted({i.rule_type for i in issues}, key=_TYPE_ORDER.index)
        else:
            what = sorted({i.operator for i in issues}, key=list(OPERATOR_VALUES).index)
        cell = ", ".join(f"`{w}`" for w in what)
        rows.append(f"| {literal(value)} | {cell} | {'; '.join(reasons)} |")
    return rows


# Rule value types in the order the operator tables show them.
_TYPE_ORDER = ["int", "float", "str", "bool", "date", "None"]


def render(result: MatrixResult | None = None) -> str:
    result = result or run_matrix()
    out: list[str] = [
        "# How FluxRules Compares Values",
        "",
        "This page shows, for every operator, which fact values match which rule "
        "values. Use it to check how a rule will treat a number stored as text, a "
        "`None`, a date, a boolean or a missing field.",
        "",
        "!!! note",
        "    This page is generated from the tests in "
        "`tests/engine/comparison_matrix.py`, which run every case on every "
        "evaluation path. Do not edit it by hand: run `make docs-tables`. A test "
        "fails when the page and the code disagree.",
        "",
        "## How a comparison works",
        "",
        "A comparison is plain Python: `v > 5` runs `fact_value > 5`. FluxRules does "
        'not convert between types, so the text `"5"` is not the number `5`. Three '
        "rules follow from that:",
        "",
        "- **A comparison Python cannot make is no match, not an error.** "
        '`"abc" > 5` raises `TypeError` in Python; in a rule it is no match, and a '
        "`ComparisonWarning` tells you. See "
        "[Comparisons that cannot be made](#comparisons-that-cannot-be-made).",
        "- **`NOT` turns that no match into a match.** `NOT(v > 5)` fires for "
        '`"abc"`, `None` and a missing field, because the check inside failed. '
        "See [NOT over a comparison](#not-over-a-comparison).",
        "- **A missing field, or a `None` value, matches nothing** unless you change "
        "the [settings](#how-each-setting-changes-the-answers).",
        "",
        "Python's own rules still apply where Python can compare: `True == 1`, "
        "`5 == 5.0`, a `Decimal` compares with a float, and `0.1 + 0.2 == 0.3` is "
        "false. `in` and `not_in` take a list; a single value counts as a one-item "
        "list (see [Conditions](conditions.md#collection-membership)).",
        "",
        "## How to read the tables",
        "",
        "Each table is one operator under the default settings. A row is the value "
        "in the fact, under the field `v`; a column is the value written in the "
        "rule. **yes** means the rule fires. `(missing)` means the fact has no `v` "
        "field at all.",
        "",
        "## Default settings",
        "",
    ]
    for op in OPERATOR_VALUES:
        out += [f"### `{op}`", "", *_operator_table(result, op), ""]
    out += [
        "## NOT over a comparison",
        "",
        "`NOT` fires whenever the check inside does not match, including when the "
        'check could not be made. That is why `NOT(v > 5)` fires for `"5"`, '
        '`"abc"`, `None`, `float("nan")`, a date and a missing field:',
        "",
        *_not_table(result),
        "",
        "To stop `NOT` from firing on a missing field, set "
        '`EngineConfig(missing_field="unknown")`. To stop it from firing on a '
        'comparison that cannot be made, set `EngineConfig(uncomparable="unknown")`. '
        "Better still, give the engine a fact schema so values arrive with the "
        "right type (see [Avoiding surprises](#avoiding-surprises)).",
        "",
        *_uncomparable_section(result),
        "## How each setting changes the answers",
        "",
        "Each table lists the answers that differ from the default settings. Where "
        "a setting changes no plain comparison, the table shows the `NOT` cases it "
        "changes instead.",
        "",
    ]
    for setting in PAGE_SETTINGS:
        out += [
            f"### `{setting}`",
            "",
            SETTING_INTROS[setting],
            "",
            *_setting_changes(result, setting),
            "",
        ]
    out += ["## Known differences between paths", ""]
    if KNOWN:
        out += [
            "Every evaluation path gives the answers above, except in these cases. "
            "Each one is a known bug, and the tests fail if it is fixed without "
            "updating this list.",
            "",
            "| Paths | Settings | What happens |",
            "|---|---|---|",
        ]
        out += [f"| {k.paths} | {k.settings} | {k.reason} |" for k in KNOWN]
    else:
        out.append(
            "None. Every evaluation path gives the answers above under every setting: "
            "`PhreakEngine` with and without the alpha prefilter, compiled conditions, "
            "streaming mode, the thread pool, `evaluate_batch` in this process and over worker "
            "processes, `fluxrules.evaluate()`, `CrossFactEngine` (for the rules it "
            "can express), `PreFilteredEvaluator` over a SQL fact store, the CLI and "
            "the HTTP API. The answers are also the same whether a rule is written as "
            "a dict, as an `F` expression or in a YAML file. The tests fail if any of "
            "them starts to differ."
        )
    out += [
        "",
        "## Avoiding surprises",
        "",
        "- **Give the engine a fact schema.** With `fact_schema=` and "
        '`validate_facts="normalize"`, the text `"100.3"` becomes the number '
        '`100.3` before any rule runs; with `validate_facts="strict"`, a wrong type '
        "raises `FactValidationError` instead of quietly not matching. See "
        "[Typed Facts](typed-facts.md).",
        "- **Or convert in a pipeline.** The `FieldType` transform converts named "
        "fields of a plain dict. See [Fact Pipeline](fact-pipeline.md).",
        "- **Use `Decimal` for money,** and avoid `==` on floats: compare with `>=` "
        "or `<=` instead.",
        "- **Parse dates first.** An ISO date string is text, and a `date` does not "
        "compare with a `datetime`.",
        "- **Write `in` values as a list,** and use `==` when you mean one value.",
        "- **Check rules before they run.** With a fact schema, `load_rules` refuses "
        'a rule value of the wrong type for its field, such as the text `"100.1"` '
        "for a `float` field, and loads an ISO date string on a `date` field as a "
        "date. `fluxrules.validate()` and `fluxrules validate` list every such "
        "problem. See [Rule values are checked too]"
        "(typed-facts.md#rule-values-are-checked-too).",
        "",
    ]
    return "\n".join(out)


def write() -> Path:
    PAGE.write_text(render())
    return PAGE
