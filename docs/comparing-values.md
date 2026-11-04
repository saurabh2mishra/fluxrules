# How FluxRules Compares Values

This page shows, for every operator, which fact values match which rule values. Use it to check how a rule will treat a number stored as text, a `None`, a date, a boolean or a missing field.

!!! note
    This page is generated from the tests in `tests/engine/comparison_matrix.py`, which run every case on every evaluation path. Do not edit it by hand: run `make docs-tables`. A test fails when the page and the code disagree.

## How a comparison works

A comparison is plain Python: `v > 5` runs `fact_value > 5`. FluxRules does not convert between types, so the text `"5"` is not the number `5`. Three rules follow from that:

- **A comparison Python cannot make is no match, not an error.** `"abc" > 5` raises `TypeError` in Python; in a rule it is no match, and a `ComparisonWarning` tells you. See [Comparisons that cannot be made](#comparisons-that-cannot-be-made).
- **`NOT` turns that no match into a match.** `NOT(v > 5)` fires for `"abc"`, `None` and a missing field, because the check inside failed. See [NOT over a comparison](#not-over-a-comparison).
- **A missing field, or a `None` value, matches nothing** unless you change the [settings](#how-each-setting-changes-the-answers).

Python's own rules still apply where Python can compare: `True == 1`, `5 == 5.0`, a `Decimal` compares with a float, and `0.1 + 0.2 == 0.3` is false. `in` and `not_in` take a list; a single value counts as a one-item list (see [Conditions](conditions.md#collection-membership)).

## How to read the tables

Each table is one operator under the default settings. A row is the value in the fact, under the field `v`; a column is the value written in the rule. **yes** means the rule fires. `(missing)` means the fact has no `v` field at all.

## Default settings

### `==`

| Fact value | `5` | `5.5` | `"5"` | `"abc"` | `True` | `date(2026, 1, 1)` | `None` |
|---|---|---|---|---|---|---|---|
| `5` | yes | no | no | no | no | no | no |
| `0` | no | no | no | no | no | no | no |
| `5.5` | no | yes | no | no | no | no | no |
| `Decimal("5.5")` | no | yes | no | no | no | no | no |
| `True` | no | no | no | no | yes | no | no |
| `False` | no | no | no | no | no | no | no |
| `"5"` | no | no | yes | no | no | no | no |
| `"true"` | no | no | no | no | no | no | no |
| `"abc"` | no | no | no | yes | no | no | no |
| `""` | no | no | no | no | no | no | no |
| `None` | no | no | no | no | no | no | no |
| `float("nan")` | no | no | no | no | no | no | no |
| `Decimal("NaN")` | no | no | no | no | no | no | no |
| `float("inf")` | no | no | no | no | no | no | no |
| `date(2026, 6, 1)` | no | no | no | no | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no | no | no | no | no |
| `"2026-06-01"` | no | no | no | no | no | no | no |
| `[5]` | no | no | no | no | no | no | no |
| `(5,)` | no | no | no | no | no | no | no |
| `{"a": 5}` | no | no | no | no | no | no | no |
| (missing) | no | no | no | no | no | no | no |

### `!=`

| Fact value | `5` | `5.5` | `"5"` | `"abc"` | `True` | `date(2026, 1, 1)` | `None` |
|---|---|---|---|---|---|---|---|
| `5` | no | yes | yes | yes | yes | yes | yes |
| `0` | yes | yes | yes | yes | yes | yes | yes |
| `5.5` | yes | no | yes | yes | yes | yes | yes |
| `Decimal("5.5")` | yes | no | yes | yes | yes | yes | yes |
| `True` | yes | yes | yes | yes | no | yes | yes |
| `False` | yes | yes | yes | yes | yes | yes | yes |
| `"5"` | yes | yes | no | yes | yes | yes | yes |
| `"true"` | yes | yes | yes | yes | yes | yes | yes |
| `"abc"` | yes | yes | yes | no | yes | yes | yes |
| `""` | yes | yes | yes | yes | yes | yes | yes |
| `None` | no | no | no | no | no | no | no |
| `float("nan")` | yes | yes | yes | yes | yes | yes | yes |
| `Decimal("NaN")` | yes | yes | yes | yes | yes | yes | yes |
| `float("inf")` | yes | yes | yes | yes | yes | yes | yes |
| `date(2026, 6, 1)` | yes | yes | yes | yes | yes | yes | yes |
| `datetime(2026, 6, 1, 12, 0)` | yes | yes | yes | yes | yes | yes | yes |
| `"2026-06-01"` | yes | yes | yes | yes | yes | yes | yes |
| `[5]` | yes | yes | yes | yes | yes | yes | yes |
| `(5,)` | yes | yes | yes | yes | yes | yes | yes |
| `{"a": 5}` | yes | yes | yes | yes | yes | yes | yes |
| (missing) | no | no | no | no | no | no | no |

### `>`

| Fact value | `5` | `5.5` | `"5"` | `"abc"` | `True` | `date(2026, 1, 1)` | `None` |
|---|---|---|---|---|---|---|---|
| `5` | no | no | no | no | yes | no | no |
| `0` | no | no | no | no | no | no | no |
| `5.5` | yes | no | no | no | yes | no | no |
| `Decimal("5.5")` | yes | no | no | no | yes | no | no |
| `True` | no | no | no | no | no | no | no |
| `False` | no | no | no | no | no | no | no |
| `"5"` | no | no | no | no | no | no | no |
| `"true"` | no | no | yes | yes | no | no | no |
| `"abc"` | no | no | yes | no | no | no | no |
| `""` | no | no | no | no | no | no | no |
| `None` | no | no | no | no | no | no | no |
| `float("nan")` | no | no | no | no | no | no | no |
| `Decimal("NaN")` | no | no | no | no | no | no | no |
| `float("inf")` | yes | yes | no | no | yes | no | no |
| `date(2026, 6, 1)` | no | no | no | no | no | yes | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no | no | no | no | no |
| `"2026-06-01"` | no | no | no | no | no | no | no |
| `[5]` | no | no | no | no | no | no | no |
| `(5,)` | no | no | no | no | no | no | no |
| `{"a": 5}` | no | no | no | no | no | no | no |
| (missing) | no | no | no | no | no | no | no |

### `>=`

| Fact value | `5` | `5.5` | `"5"` | `"abc"` | `True` | `date(2026, 1, 1)` | `None` |
|---|---|---|---|---|---|---|---|
| `5` | yes | no | no | no | yes | no | no |
| `0` | no | no | no | no | no | no | no |
| `5.5` | yes | yes | no | no | yes | no | no |
| `Decimal("5.5")` | yes | yes | no | no | yes | no | no |
| `True` | no | no | no | no | yes | no | no |
| `False` | no | no | no | no | no | no | no |
| `"5"` | no | no | yes | no | no | no | no |
| `"true"` | no | no | yes | yes | no | no | no |
| `"abc"` | no | no | yes | yes | no | no | no |
| `""` | no | no | no | no | no | no | no |
| `None` | no | no | no | no | no | no | no |
| `float("nan")` | no | no | no | no | no | no | no |
| `Decimal("NaN")` | no | no | no | no | no | no | no |
| `float("inf")` | yes | yes | no | no | yes | no | no |
| `date(2026, 6, 1)` | no | no | no | no | no | yes | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no | no | no | no | no |
| `"2026-06-01"` | no | no | no | no | no | no | no |
| `[5]` | no | no | no | no | no | no | no |
| `(5,)` | no | no | no | no | no | no | no |
| `{"a": 5}` | no | no | no | no | no | no | no |
| (missing) | no | no | no | no | no | no | no |

### `<`

| Fact value | `5` | `5.5` | `"5"` | `"abc"` | `True` | `date(2026, 1, 1)` | `None` |
|---|---|---|---|---|---|---|---|
| `5` | no | yes | no | no | no | no | no |
| `0` | yes | yes | no | no | yes | no | no |
| `5.5` | no | no | no | no | no | no | no |
| `Decimal("5.5")` | no | no | no | no | no | no | no |
| `True` | yes | yes | no | no | no | no | no |
| `False` | yes | yes | no | no | yes | no | no |
| `"5"` | no | no | no | yes | no | no | no |
| `"true"` | no | no | no | no | no | no | no |
| `"abc"` | no | no | no | no | no | no | no |
| `""` | no | no | yes | yes | no | no | no |
| `None` | no | no | no | no | no | no | no |
| `float("nan")` | no | no | no | no | no | no | no |
| `Decimal("NaN")` | no | no | no | no | no | no | no |
| `float("inf")` | no | no | no | no | no | no | no |
| `date(2026, 6, 1)` | no | no | no | no | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no | no | no | no | no |
| `"2026-06-01"` | no | no | yes | yes | no | no | no |
| `[5]` | no | no | no | no | no | no | no |
| `(5,)` | no | no | no | no | no | no | no |
| `{"a": 5}` | no | no | no | no | no | no | no |
| (missing) | no | no | no | no | no | no | no |

### `<=`

| Fact value | `5` | `5.5` | `"5"` | `"abc"` | `True` | `date(2026, 1, 1)` | `None` |
|---|---|---|---|---|---|---|---|
| `5` | yes | yes | no | no | no | no | no |
| `0` | yes | yes | no | no | yes | no | no |
| `5.5` | no | yes | no | no | no | no | no |
| `Decimal("5.5")` | no | yes | no | no | no | no | no |
| `True` | yes | yes | no | no | yes | no | no |
| `False` | yes | yes | no | no | yes | no | no |
| `"5"` | no | no | yes | yes | no | no | no |
| `"true"` | no | no | no | no | no | no | no |
| `"abc"` | no | no | no | yes | no | no | no |
| `""` | no | no | yes | yes | no | no | no |
| `None` | no | no | no | no | no | no | no |
| `float("nan")` | no | no | no | no | no | no | no |
| `Decimal("NaN")` | no | no | no | no | no | no | no |
| `float("inf")` | no | no | no | no | no | no | no |
| `date(2026, 6, 1)` | no | no | no | no | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no | no | no | no | no |
| `"2026-06-01"` | no | no | yes | yes | no | no | no |
| `[5]` | no | no | no | no | no | no | no |
| `(5,)` | no | no | no | no | no | no | no |
| `{"a": 5}` | no | no | no | no | no | no | no |
| (missing) | no | no | no | no | no | no | no |

### `in`

| Fact value | `[5, "abc"]` | `[True]` | `[None]` | `"abc"` | `[{"a": 5}, [5]]` | `{"a": 5}` |
|---|---|---|---|---|---|---|
| `5` | yes | no | no | no | no | no |
| `0` | no | no | no | no | no | no |
| `5.5` | no | no | no | no | no | no |
| `Decimal("5.5")` | no | no | no | no | no | no |
| `True` | no | yes | no | no | no | no |
| `False` | no | no | no | no | no | no |
| `"5"` | no | no | no | no | no | no |
| `"true"` | no | no | no | no | no | no |
| `"abc"` | yes | no | no | yes | no | no |
| `""` | no | no | no | no | no | no |
| `None` | no | no | no | no | no | no |
| `float("nan")` | no | no | no | no | no | no |
| `Decimal("NaN")` | no | no | no | no | no | no |
| `float("inf")` | no | no | no | no | no | no |
| `date(2026, 6, 1)` | no | no | no | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no | no | no | no |
| `"2026-06-01"` | no | no | no | no | no | no |
| `[5]` | no | no | no | no | yes | no |
| `(5,)` | no | no | no | no | no | no |
| `{"a": 5}` | no | no | no | no | yes | yes |
| (missing) | no | no | no | no | no | no |

### `not_in`

| Fact value | `[5, "abc"]` | `[True]` | `[None]` | `"abc"` | `[{"a": 5}, [5]]` | `{"a": 5}` |
|---|---|---|---|---|---|---|
| `5` | no | yes | yes | yes | yes | yes |
| `0` | yes | yes | yes | yes | yes | yes |
| `5.5` | yes | yes | yes | yes | yes | yes |
| `Decimal("5.5")` | yes | yes | yes | yes | yes | yes |
| `True` | yes | no | yes | yes | yes | yes |
| `False` | yes | yes | yes | yes | yes | yes |
| `"5"` | yes | yes | yes | yes | yes | yes |
| `"true"` | yes | yes | yes | yes | yes | yes |
| `"abc"` | no | yes | yes | no | yes | yes |
| `""` | yes | yes | yes | yes | yes | yes |
| `None` | no | no | no | no | no | no |
| `float("nan")` | yes | yes | yes | yes | yes | yes |
| `Decimal("NaN")` | yes | yes | yes | yes | yes | yes |
| `float("inf")` | yes | yes | yes | yes | yes | yes |
| `date(2026, 6, 1)` | yes | yes | yes | yes | yes | yes |
| `datetime(2026, 6, 1, 12, 0)` | yes | yes | yes | yes | yes | yes |
| `"2026-06-01"` | yes | yes | yes | yes | yes | yes |
| `[5]` | yes | yes | yes | yes | no | yes |
| `(5,)` | yes | yes | yes | yes | yes | yes |
| `{"a": 5}` | yes | yes | yes | yes | no | no |
| (missing) | no | no | no | no | no | no |

### `contains`

| Fact value | `"a"` | `"5"` | `"("` |
|---|---|---|---|
| `5` | no | no | no |
| `0` | no | no | no |
| `5.5` | no | no | no |
| `Decimal("5.5")` | no | no | no |
| `True` | no | no | no |
| `False` | no | no | no |
| `"5"` | no | yes | no |
| `"true"` | no | no | no |
| `"abc"` | yes | no | no |
| `""` | no | no | no |
| `None` | no | no | no |
| `float("nan")` | no | no | no |
| `Decimal("NaN")` | no | no | no |
| `float("inf")` | no | no | no |
| `date(2026, 6, 1)` | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no |
| `"2026-06-01"` | no | no | no |
| `[5]` | no | no | no |
| `(5,)` | no | no | no |
| `{"a": 5}` | yes | no | no |
| (missing) | no | no | no |

### `not_contains`

| Fact value | `"a"` | `"5"` | `"("` |
|---|---|---|---|
| `5` | no | no | no |
| `0` | no | no | no |
| `5.5` | no | no | no |
| `Decimal("5.5")` | no | no | no |
| `True` | no | no | no |
| `False` | no | no | no |
| `"5"` | yes | no | yes |
| `"true"` | yes | yes | yes |
| `"abc"` | no | yes | yes |
| `""` | yes | yes | yes |
| `None` | no | no | no |
| `float("nan")` | no | no | no |
| `Decimal("NaN")` | no | no | no |
| `float("inf")` | no | no | no |
| `date(2026, 6, 1)` | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no |
| `"2026-06-01"` | yes | yes | yes |
| `[5]` | yes | yes | yes |
| `(5,)` | yes | yes | yes |
| `{"a": 5}` | no | yes | yes |
| (missing) | no | no | no |

### `starts_with`

| Fact value | `"a"` | `"5"` | `"("` |
|---|---|---|---|
| `5` | no | yes | no |
| `0` | no | no | no |
| `5.5` | no | yes | no |
| `Decimal("5.5")` | no | yes | no |
| `True` | no | no | no |
| `False` | no | no | no |
| `"5"` | no | yes | no |
| `"true"` | no | no | no |
| `"abc"` | yes | no | no |
| `""` | no | no | no |
| `None` | no | no | no |
| `float("nan")` | no | no | no |
| `Decimal("NaN")` | no | no | no |
| `float("inf")` | no | no | no |
| `date(2026, 6, 1)` | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no |
| `"2026-06-01"` | no | no | no |
| `[5]` | no | no | no |
| `(5,)` | no | no | yes |
| `{"a": 5}` | no | no | no |
| (missing) | no | no | no |

### `ends_with`

| Fact value | `"a"` | `"5"` | `"("` |
|---|---|---|---|
| `5` | no | yes | no |
| `0` | no | no | no |
| `5.5` | no | yes | no |
| `Decimal("5.5")` | no | yes | no |
| `True` | no | no | no |
| `False` | no | no | no |
| `"5"` | no | yes | no |
| `"true"` | no | no | no |
| `"abc"` | no | no | no |
| `""` | no | no | no |
| `None` | no | no | no |
| `float("nan")` | no | no | no |
| `Decimal("NaN")` | no | no | no |
| `float("inf")` | no | no | no |
| `date(2026, 6, 1)` | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no |
| `"2026-06-01"` | no | no | no |
| `[5]` | no | no | no |
| `(5,)` | no | no | no |
| `{"a": 5}` | no | no | no |
| (missing) | no | no | no |

### `regex`

| Fact value | `"a"` | `"5"` | `"("` |
|---|---|---|---|
| `5` | no | yes | no |
| `0` | no | no | no |
| `5.5` | no | yes | no |
| `Decimal("5.5")` | no | yes | no |
| `True` | no | no | no |
| `False` | yes | no | no |
| `"5"` | no | yes | no |
| `"true"` | no | no | no |
| `"abc"` | yes | no | no |
| `""` | no | no | no |
| `None` | no | no | no |
| `float("nan")` | yes | no | no |
| `Decimal("NaN")` | yes | no | no |
| `float("inf")` | no | no | no |
| `date(2026, 6, 1)` | no | no | no |
| `datetime(2026, 6, 1, 12, 0)` | no | no | no |
| `"2026-06-01"` | no | no | no |
| `[5]` | no | yes | no |
| `(5,)` | no | yes | no |
| `{"a": 5}` | yes | yes | no |
| (missing) | no | no | no |

## NOT over a comparison

`NOT` fires whenever the check inside does not match, including when the check could not be made. That is why `NOT(v > 5)` fires for `"5"`, `"abc"`, `None`, `float("nan")`, a date and a missing field:

| Fact value | `NOT(v == 5)` | `NOT(v != 5)` | `NOT(v > 5)` | `NOT(v >= 5)` | `NOT(v < 5)` | `NOT(v <= 5)` |
|---|---|---|---|---|---|---|
| `5` | no | yes | yes | no | yes | no |
| `0` | yes | no | yes | yes | no | no |
| `5.5` | yes | no | no | no | yes | yes |
| `Decimal("5.5")` | yes | no | no | no | yes | yes |
| `True` | yes | no | yes | yes | no | no |
| `False` | yes | no | yes | yes | no | no |
| `"5"` | yes | no | yes | yes | yes | yes |
| `"true"` | yes | no | yes | yes | yes | yes |
| `"abc"` | yes | no | yes | yes | yes | yes |
| `""` | yes | no | yes | yes | yes | yes |
| `None` | yes | yes | yes | yes | yes | yes |
| `float("nan")` | yes | no | yes | yes | yes | yes |
| `Decimal("NaN")` | yes | no | yes | yes | yes | yes |
| `float("inf")` | yes | no | no | no | yes | yes |
| `date(2026, 6, 1)` | yes | no | yes | yes | yes | yes |
| `datetime(2026, 6, 1, 12, 0)` | yes | no | yes | yes | yes | yes |
| `"2026-06-01"` | yes | no | yes | yes | yes | yes |
| `[5]` | yes | no | yes | yes | yes | yes |
| `(5,)` | yes | no | yes | yes | yes | yes |
| `{"a": 5}` | yes | no | yes | yes | yes | yes |
| (missing) | yes | yes | yes | yes | yes | yes |

To stop `NOT` from firing on a missing field, set `EngineConfig(missing_field="unknown")`. To stop it from firing on a comparison that cannot be made, set `EngineConfig(uncomparable="unknown")`. Better still, give the engine a fact schema so values arrive with the right type (see [Avoiding surprises](#avoiding-surprises)).

## Comparisons that cannot be made

Some comparisons have no answer: `"abc" > 5`, `None > 5`, `float("nan") > 5`, a `date` against a `datetime`, `contains` on a number, an invalid regex. The condition is no match, as the tables above show. When such a comparison leaves a rule undecided, the result lists it in `comparison_issues`, with the field, the operator, both types and the reason, and `EngineConfig(uncomparable=...)` chooses what else happens:

| `uncomparable` | What happens |
|---|---|
| `None` (default) | No match, and a `ComparisonWarning` once per field, operator and pair of types. |
| `"false"` | No match, with no warning. |
| `"unknown"` | Unknown: a rule fires only when its condition is definitely true, so `NOT` over it does not fire. |
| `"raise"` | `UncomparableValuesError`, naming the field, the operator and both types. |

A comparison that decides nothing is not reported: in `(F("v") > 5) & (F("country") == "US")` with `country` set to `"DE"`, the rule is no match whatever `v` holds, so `v = "abc"` is not reported. `==` and `!=` always have an answer: different values, `None`, `NaN` and values of different types are not equal.

These are every comparison in the tables above that has no answer, under the default settings:

| Fact value | Cannot be ordered (`>`, `>=`, `<`, `<=`) against | Why |
|---|---|---|
| `5` | `str`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `0` | `str`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `5.5` | `str`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `Decimal("5.5")` | `str`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `True` | `str`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `False` | `str`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `"5"` | `int`, `float`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `"true"` | `int`, `float`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `"abc"` | `int`, `float`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `""` | `int`, `float`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `None` | `int`, `float`, `str`, `bool`, `date`, `None` | None cannot be ordered |
| `float("nan")` | `int`, `float`, `str`, `bool`, `date`, `None` | NaN cannot be ordered; None cannot be ordered |
| `Decimal("NaN")` | `int`, `float`, `str`, `bool`, `date`, `None` | NaN cannot be ordered; None cannot be ordered |
| `float("inf")` | `str`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `date(2026, 6, 1)` | `int`, `float`, `str`, `bool`, `None` | None cannot be ordered; these types cannot be ordered |
| `datetime(2026, 6, 1, 12, 0)` | `int`, `float`, `str`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `"2026-06-01"` | `int`, `float`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `[5]` | `int`, `float`, `str`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `(5,)` | `int`, `float`, `str`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |
| `{"a": 5}` | `int`, `float`, `str`, `bool`, `date`, `None` | None cannot be ordered; these types cannot be ordered |

| Fact value | Operator | Why |
|---|---|---|
| `5` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `0` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `5.5` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `Decimal("5.5")` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `True` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `False` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `"5"` | `regex` | the rule value is not a valid regular expression |
| `"true"` | `regex` | the rule value is not a valid regular expression |
| `"abc"` | `regex` | the rule value is not a valid regular expression |
| `""` | `regex` | the rule value is not a valid regular expression |
| `float("nan")` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `Decimal("NaN")` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `float("inf")` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `date(2026, 6, 1)` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `datetime(2026, 6, 1, 12, 0)` | `contains`, `not_contains`, `regex` | the fact value cannot contain the rule value; the rule value is not a valid regular expression |
| `"2026-06-01"` | `regex` | the rule value is not a valid regular expression |
| `[5]` | `regex` | the rule value is not a valid regular expression |
| `(5,)` | `regex` | the rule value is not a valid regular expression |
| `{"a": 5}` | `regex` | the rule value is not a valid regular expression |

## How each setting changes the answers

Each table lists the answers that differ from the default settings. Where a setting changes no plain comparison, the table shows the `NOT` cases it changes instead.

### `strict_null_handling`

`EngineConfig(strict_null_handling=True)` lets `== None` match a `None` value and `!= x` match it too. By default a `None` value never matches.

| Rule | Fact value | Default | With this setting |
|---|---|---|---|
| `v == None` | `None` | no | yes |
| `v != 5` | `None` | no | yes |
| `v != 5.5` | `None` | no | yes |
| `v != "5"` | `None` | no | yes |
| `v != "abc"` | `None` | no | yes |
| `v != True` | `None` | no | yes |
| `v != date(2026, 1, 1)` | `None` | no | yes |

### `strict_type_comparison`

`EngineConfig(strict_type_comparison=True)` treats values of different types as never equal, and a boolean as a different type from a number: `5 == "5"` is no match and `5 != "5"` is a match. It orders (`>`, `<` and the like) two numbers only; any other ordering cannot be made, so it is no match and is reported (see [Comparisons that cannot be made](#comparisons-that-cannot-be-made)).

| Rule | Fact value | Default | With this setting |
|---|---|---|---|
| `v == 5.5` | `Decimal("5.5")` | yes | no |
| `v != 5.5` | `Decimal("5.5")` | no | yes |
| `v > 5` | `Decimal("5.5")` | yes | no |
| `v > "5"` | `"true"` | yes | no |
| `v > "5"` | `"abc"` | yes | no |
| `v > "abc"` | `"true"` | yes | no |
| `v > True` | `5` | yes | no |
| `v > True` | `5.5` | yes | no |
| `v > True` | `Decimal("5.5")` | yes | no |
| `v > True` | `float("inf")` | yes | no |
| `v > date(2026, 1, 1)` | `date(2026, 6, 1)` | yes | no |
| `v >= 5` | `Decimal("5.5")` | yes | no |
| `v >= 5.5` | `Decimal("5.5")` | yes | no |
| `v >= "5"` | `"5"` | yes | no |
| `v >= "5"` | `"true"` | yes | no |
| `v >= "5"` | `"abc"` | yes | no |
| `v >= "abc"` | `"true"` | yes | no |
| `v >= "abc"` | `"abc"` | yes | no |
| `v >= True` | `5` | yes | no |
| `v >= True` | `5.5` | yes | no |
| `v >= True` | `Decimal("5.5")` | yes | no |
| `v >= True` | `True` | yes | no |
| `v >= True` | `float("inf")` | yes | no |
| `v >= date(2026, 1, 1)` | `date(2026, 6, 1)` | yes | no |
| `v < 5` | `True` | yes | no |
| `v < 5` | `False` | yes | no |
| `v < 5.5` | `True` | yes | no |
| `v < 5.5` | `False` | yes | no |
| `v < "5"` | `""` | yes | no |
| `v < "5"` | `"2026-06-01"` | yes | no |
| `v < "abc"` | `"5"` | yes | no |
| `v < "abc"` | `""` | yes | no |
| `v < "abc"` | `"2026-06-01"` | yes | no |
| `v < True` | `0` | yes | no |
| `v < True` | `False` | yes | no |
| `v <= 5` | `True` | yes | no |
| `v <= 5` | `False` | yes | no |
| `v <= 5.5` | `Decimal("5.5")` | yes | no |
| `v <= 5.5` | `True` | yes | no |
| `v <= 5.5` | `False` | yes | no |
| `v <= "5"` | `"5"` | yes | no |
| `v <= "5"` | `""` | yes | no |
| `v <= "5"` | `"2026-06-01"` | yes | no |
| `v <= "abc"` | `"5"` | yes | no |
| `v <= "abc"` | `"abc"` | yes | no |
| `v <= "abc"` | `""` | yes | no |
| `v <= "abc"` | `"2026-06-01"` | yes | no |
| `v <= True` | `0` | yes | no |
| `v <= True` | `True` | yes | no |
| `v <= True` | `False` | yes | no |

### `boolean_string_coercion`

`EngineConfig(boolean_string_coercion=True)` reads the strings `"true"` and `"false"` (in any case) as `True` and `False`, on both the fact side and the rule side, before any operator runs, including the text operators.

| Rule | Fact value | Default | With this setting |
|---|---|---|---|
| `v == True` | `"true"` | no | yes |
| `v != True` | `"true"` | yes | no |
| `v > "5"` | `"true"` | yes | no |
| `v > "abc"` | `"true"` | yes | no |
| `v >= "5"` | `"true"` | yes | no |
| `v >= "abc"` | `"true"` | yes | no |
| `v >= True` | `"true"` | no | yes |
| `v < 5` | `"true"` | no | yes |
| `v < 5.5` | `"true"` | no | yes |
| `v <= 5` | `"true"` | no | yes |
| `v <= 5.5` | `"true"` | no | yes |
| `v <= True` | `"true"` | no | yes |
| `v in [True]` | `"true"` | no | yes |
| `v not_in [True]` | `"true"` | yes | no |
| `v not_contains "a"` | `"true"` | yes | no |
| `v not_contains "5"` | `"true"` | yes | no |
| `v not_contains "("` | `"true"` | yes | no |

### `missing_field=unknown`

`EngineConfig(missing_field="unknown")` treats a missing field as unknown rather than as a failed check, so `NOT` over it does not fire. This becomes the default in 2.0. It changes no plain comparison, only `NOT`.

| Rule | Fact value | Default | With this setting |
|---|---|---|---|
| `NOT(v == 5)` | (missing) | yes | no |
| `NOT(v == 5.5)` | (missing) | yes | no |
| `NOT(v == "5")` | (missing) | yes | no |
| `NOT(v == "abc")` | (missing) | yes | no |
| `NOT(v == True)` | (missing) | yes | no |
| `NOT(v == date(2026, 1, 1))` | (missing) | yes | no |
| `NOT(v == None)` | (missing) | yes | no |
| `NOT(v != 5)` | (missing) | yes | no |
| `NOT(v != 5.5)` | (missing) | yes | no |
| `NOT(v != "5")` | (missing) | yes | no |
| `NOT(v != "abc")` | (missing) | yes | no |
| `NOT(v != True)` | (missing) | yes | no |
| `NOT(v != date(2026, 1, 1))` | (missing) | yes | no |
| `NOT(v != None)` | (missing) | yes | no |
| `NOT(v > 5)` | (missing) | yes | no |
| `NOT(v > 5.5)` | (missing) | yes | no |
| `NOT(v > "5")` | (missing) | yes | no |
| `NOT(v > "abc")` | (missing) | yes | no |
| `NOT(v > True)` | (missing) | yes | no |
| `NOT(v > date(2026, 1, 1))` | (missing) | yes | no |
| `NOT(v > None)` | (missing) | yes | no |
| `NOT(v >= 5)` | (missing) | yes | no |
| `NOT(v >= 5.5)` | (missing) | yes | no |
| `NOT(v >= "5")` | (missing) | yes | no |
| `NOT(v >= "abc")` | (missing) | yes | no |
| `NOT(v >= True)` | (missing) | yes | no |
| `NOT(v >= date(2026, 1, 1))` | (missing) | yes | no |
| `NOT(v >= None)` | (missing) | yes | no |
| `NOT(v < 5)` | (missing) | yes | no |
| `NOT(v < 5.5)` | (missing) | yes | no |
| `NOT(v < "5")` | (missing) | yes | no |
| `NOT(v < "abc")` | (missing) | yes | no |
| `NOT(v < True)` | (missing) | yes | no |
| `NOT(v < date(2026, 1, 1))` | (missing) | yes | no |
| `NOT(v < None)` | (missing) | yes | no |
| `NOT(v <= 5)` | (missing) | yes | no |
| `NOT(v <= 5.5)` | (missing) | yes | no |
| `NOT(v <= "5")` | (missing) | yes | no |
| `NOT(v <= "abc")` | (missing) | yes | no |
| `NOT(v <= True)` | (missing) | yes | no |
| `NOT(v <= date(2026, 1, 1))` | (missing) | yes | no |
| `NOT(v <= None)` | (missing) | yes | no |
| `NOT(v in [5, "abc"])` | (missing) | yes | no |
| `NOT(v in [True])` | (missing) | yes | no |
| `NOT(v in [None])` | (missing) | yes | no |
| `NOT(v in "abc")` | (missing) | yes | no |
| `NOT(v in [{"a": 5}, [5]])` | (missing) | yes | no |
| `NOT(v in {"a": 5})` | (missing) | yes | no |
| `NOT(v not_in [5, "abc"])` | (missing) | yes | no |
| `NOT(v not_in [True])` | (missing) | yes | no |
| `NOT(v not_in [None])` | (missing) | yes | no |
| `NOT(v not_in "abc")` | (missing) | yes | no |
| `NOT(v not_in [{"a": 5}, [5]])` | (missing) | yes | no |
| `NOT(v not_in {"a": 5})` | (missing) | yes | no |
| `NOT(v contains "a")` | (missing) | yes | no |
| `NOT(v contains "5")` | (missing) | yes | no |
| `NOT(v contains "(")` | (missing) | yes | no |
| `NOT(v not_contains "a")` | (missing) | yes | no |
| `NOT(v not_contains "5")` | (missing) | yes | no |
| `NOT(v not_contains "(")` | (missing) | yes | no |
| `NOT(v starts_with "a")` | (missing) | yes | no |
| `NOT(v starts_with "5")` | (missing) | yes | no |
| `NOT(v starts_with "(")` | (missing) | yes | no |
| `NOT(v ends_with "a")` | (missing) | yes | no |
| `NOT(v ends_with "5")` | (missing) | yes | no |
| `NOT(v ends_with "(")` | (missing) | yes | no |
| `NOT(v regex "a")` | (missing) | yes | no |
| `NOT(v regex "5")` | (missing) | yes | no |
| `NOT(v regex "(")` | (missing) | yes | no |

### `missing_field=false`

`EngineConfig(missing_field="false")` keeps the 1.x behaviour, where `NOT` over a missing field fires, and turns off the warning about it.

With the matrix's rules and facts, this setting changes no answers.

### `uncomparable=unknown`

`EngineConfig(uncomparable="unknown")` treats a comparison that cannot be made as unknown rather than as a failed check, so a rule fires only when its condition is definitely true: `NOT` over such a comparison does not fire. It changes no plain comparison, only `NOT`.

| Rule | Fact value | Default | With this setting |
|---|---|---|---|
| `NOT(v > 5)` | `"5"` | yes | no |
| `NOT(v > 5)` | `"true"` | yes | no |
| `NOT(v > 5)` | `"abc"` | yes | no |
| `NOT(v > 5)` | `""` | yes | no |
| `NOT(v > 5)` | `None` | yes | no |
| `NOT(v > 5)` | `float("nan")` | yes | no |
| `NOT(v > 5)` | `Decimal("NaN")` | yes | no |
| `NOT(v > 5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v > 5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v > 5)` | `"2026-06-01"` | yes | no |
| `NOT(v > 5)` | `[5]` | yes | no |
| `NOT(v > 5)` | `(5,)` | yes | no |
| `NOT(v > 5)` | `{"a": 5}` | yes | no |
| `NOT(v > 5.5)` | `"5"` | yes | no |
| `NOT(v > 5.5)` | `"true"` | yes | no |
| `NOT(v > 5.5)` | `"abc"` | yes | no |
| `NOT(v > 5.5)` | `""` | yes | no |
| `NOT(v > 5.5)` | `None` | yes | no |
| `NOT(v > 5.5)` | `float("nan")` | yes | no |
| `NOT(v > 5.5)` | `Decimal("NaN")` | yes | no |
| `NOT(v > 5.5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v > 5.5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v > 5.5)` | `"2026-06-01"` | yes | no |
| `NOT(v > 5.5)` | `[5]` | yes | no |
| `NOT(v > 5.5)` | `(5,)` | yes | no |
| `NOT(v > 5.5)` | `{"a": 5}` | yes | no |
| `NOT(v > "5")` | `5` | yes | no |
| `NOT(v > "5")` | `0` | yes | no |
| `NOT(v > "5")` | `5.5` | yes | no |
| `NOT(v > "5")` | `Decimal("5.5")` | yes | no |
| `NOT(v > "5")` | `True` | yes | no |
| `NOT(v > "5")` | `False` | yes | no |
| `NOT(v > "5")` | `None` | yes | no |
| `NOT(v > "5")` | `float("nan")` | yes | no |
| `NOT(v > "5")` | `Decimal("NaN")` | yes | no |
| `NOT(v > "5")` | `float("inf")` | yes | no |
| `NOT(v > "5")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v > "5")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v > "5")` | `[5]` | yes | no |
| `NOT(v > "5")` | `(5,)` | yes | no |
| `NOT(v > "5")` | `{"a": 5}` | yes | no |
| `NOT(v > "abc")` | `5` | yes | no |
| `NOT(v > "abc")` | `0` | yes | no |
| `NOT(v > "abc")` | `5.5` | yes | no |
| `NOT(v > "abc")` | `Decimal("5.5")` | yes | no |
| `NOT(v > "abc")` | `True` | yes | no |
| `NOT(v > "abc")` | `False` | yes | no |
| `NOT(v > "abc")` | `None` | yes | no |
| `NOT(v > "abc")` | `float("nan")` | yes | no |
| `NOT(v > "abc")` | `Decimal("NaN")` | yes | no |
| `NOT(v > "abc")` | `float("inf")` | yes | no |
| `NOT(v > "abc")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v > "abc")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v > "abc")` | `[5]` | yes | no |
| `NOT(v > "abc")` | `(5,)` | yes | no |
| `NOT(v > "abc")` | `{"a": 5}` | yes | no |
| `NOT(v > True)` | `"5"` | yes | no |
| `NOT(v > True)` | `"true"` | yes | no |
| `NOT(v > True)` | `"abc"` | yes | no |
| `NOT(v > True)` | `""` | yes | no |
| `NOT(v > True)` | `None` | yes | no |
| `NOT(v > True)` | `float("nan")` | yes | no |
| `NOT(v > True)` | `Decimal("NaN")` | yes | no |
| `NOT(v > True)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v > True)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v > True)` | `"2026-06-01"` | yes | no |
| `NOT(v > True)` | `[5]` | yes | no |
| `NOT(v > True)` | `(5,)` | yes | no |
| `NOT(v > True)` | `{"a": 5}` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `5` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `0` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `5.5` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `Decimal("5.5")` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `True` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `False` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `"5"` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `"true"` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `"abc"` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `""` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `None` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `float("nan")` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `Decimal("NaN")` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `float("inf")` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `"2026-06-01"` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `[5]` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `(5,)` | yes | no |
| `NOT(v > date(2026, 1, 1))` | `{"a": 5}` | yes | no |
| `NOT(v > None)` | `5` | yes | no |
| `NOT(v > None)` | `0` | yes | no |
| `NOT(v > None)` | `5.5` | yes | no |
| `NOT(v > None)` | `Decimal("5.5")` | yes | no |
| `NOT(v > None)` | `True` | yes | no |
| `NOT(v > None)` | `False` | yes | no |
| `NOT(v > None)` | `"5"` | yes | no |
| `NOT(v > None)` | `"true"` | yes | no |
| `NOT(v > None)` | `"abc"` | yes | no |
| `NOT(v > None)` | `""` | yes | no |
| `NOT(v > None)` | `None` | yes | no |
| `NOT(v > None)` | `float("nan")` | yes | no |
| `NOT(v > None)` | `Decimal("NaN")` | yes | no |
| `NOT(v > None)` | `float("inf")` | yes | no |
| `NOT(v > None)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v > None)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v > None)` | `"2026-06-01"` | yes | no |
| `NOT(v > None)` | `[5]` | yes | no |
| `NOT(v > None)` | `(5,)` | yes | no |
| `NOT(v > None)` | `{"a": 5}` | yes | no |
| `NOT(v >= 5)` | `"5"` | yes | no |
| `NOT(v >= 5)` | `"true"` | yes | no |
| `NOT(v >= 5)` | `"abc"` | yes | no |
| `NOT(v >= 5)` | `""` | yes | no |
| `NOT(v >= 5)` | `None` | yes | no |
| `NOT(v >= 5)` | `float("nan")` | yes | no |
| `NOT(v >= 5)` | `Decimal("NaN")` | yes | no |
| `NOT(v >= 5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v >= 5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v >= 5)` | `"2026-06-01"` | yes | no |
| `NOT(v >= 5)` | `[5]` | yes | no |
| `NOT(v >= 5)` | `(5,)` | yes | no |
| `NOT(v >= 5)` | `{"a": 5}` | yes | no |
| `NOT(v >= 5.5)` | `"5"` | yes | no |
| `NOT(v >= 5.5)` | `"true"` | yes | no |
| `NOT(v >= 5.5)` | `"abc"` | yes | no |
| `NOT(v >= 5.5)` | `""` | yes | no |
| `NOT(v >= 5.5)` | `None` | yes | no |
| `NOT(v >= 5.5)` | `float("nan")` | yes | no |
| `NOT(v >= 5.5)` | `Decimal("NaN")` | yes | no |
| `NOT(v >= 5.5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v >= 5.5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v >= 5.5)` | `"2026-06-01"` | yes | no |
| `NOT(v >= 5.5)` | `[5]` | yes | no |
| `NOT(v >= 5.5)` | `(5,)` | yes | no |
| `NOT(v >= 5.5)` | `{"a": 5}` | yes | no |
| `NOT(v >= "5")` | `5` | yes | no |
| `NOT(v >= "5")` | `0` | yes | no |
| `NOT(v >= "5")` | `5.5` | yes | no |
| `NOT(v >= "5")` | `Decimal("5.5")` | yes | no |
| `NOT(v >= "5")` | `True` | yes | no |
| `NOT(v >= "5")` | `False` | yes | no |
| `NOT(v >= "5")` | `None` | yes | no |
| `NOT(v >= "5")` | `float("nan")` | yes | no |
| `NOT(v >= "5")` | `Decimal("NaN")` | yes | no |
| `NOT(v >= "5")` | `float("inf")` | yes | no |
| `NOT(v >= "5")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v >= "5")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v >= "5")` | `[5]` | yes | no |
| `NOT(v >= "5")` | `(5,)` | yes | no |
| `NOT(v >= "5")` | `{"a": 5}` | yes | no |
| `NOT(v >= "abc")` | `5` | yes | no |
| `NOT(v >= "abc")` | `0` | yes | no |
| `NOT(v >= "abc")` | `5.5` | yes | no |
| `NOT(v >= "abc")` | `Decimal("5.5")` | yes | no |
| `NOT(v >= "abc")` | `True` | yes | no |
| `NOT(v >= "abc")` | `False` | yes | no |
| `NOT(v >= "abc")` | `None` | yes | no |
| `NOT(v >= "abc")` | `float("nan")` | yes | no |
| `NOT(v >= "abc")` | `Decimal("NaN")` | yes | no |
| `NOT(v >= "abc")` | `float("inf")` | yes | no |
| `NOT(v >= "abc")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v >= "abc")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v >= "abc")` | `[5]` | yes | no |
| `NOT(v >= "abc")` | `(5,)` | yes | no |
| `NOT(v >= "abc")` | `{"a": 5}` | yes | no |
| `NOT(v >= True)` | `"5"` | yes | no |
| `NOT(v >= True)` | `"true"` | yes | no |
| `NOT(v >= True)` | `"abc"` | yes | no |
| `NOT(v >= True)` | `""` | yes | no |
| `NOT(v >= True)` | `None` | yes | no |
| `NOT(v >= True)` | `float("nan")` | yes | no |
| `NOT(v >= True)` | `Decimal("NaN")` | yes | no |
| `NOT(v >= True)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v >= True)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v >= True)` | `"2026-06-01"` | yes | no |
| `NOT(v >= True)` | `[5]` | yes | no |
| `NOT(v >= True)` | `(5,)` | yes | no |
| `NOT(v >= True)` | `{"a": 5}` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `5` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `0` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `5.5` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `Decimal("5.5")` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `True` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `False` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `"5"` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `"true"` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `"abc"` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `""` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `None` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `float("nan")` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `Decimal("NaN")` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `float("inf")` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `"2026-06-01"` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `[5]` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `(5,)` | yes | no |
| `NOT(v >= date(2026, 1, 1))` | `{"a": 5}` | yes | no |
| `NOT(v >= None)` | `5` | yes | no |
| `NOT(v >= None)` | `0` | yes | no |
| `NOT(v >= None)` | `5.5` | yes | no |
| `NOT(v >= None)` | `Decimal("5.5")` | yes | no |
| `NOT(v >= None)` | `True` | yes | no |
| `NOT(v >= None)` | `False` | yes | no |
| `NOT(v >= None)` | `"5"` | yes | no |
| `NOT(v >= None)` | `"true"` | yes | no |
| `NOT(v >= None)` | `"abc"` | yes | no |
| `NOT(v >= None)` | `""` | yes | no |
| `NOT(v >= None)` | `None` | yes | no |
| `NOT(v >= None)` | `float("nan")` | yes | no |
| `NOT(v >= None)` | `Decimal("NaN")` | yes | no |
| `NOT(v >= None)` | `float("inf")` | yes | no |
| `NOT(v >= None)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v >= None)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v >= None)` | `"2026-06-01"` | yes | no |
| `NOT(v >= None)` | `[5]` | yes | no |
| `NOT(v >= None)` | `(5,)` | yes | no |
| `NOT(v >= None)` | `{"a": 5}` | yes | no |
| `NOT(v < 5)` | `"5"` | yes | no |
| `NOT(v < 5)` | `"true"` | yes | no |
| `NOT(v < 5)` | `"abc"` | yes | no |
| `NOT(v < 5)` | `""` | yes | no |
| `NOT(v < 5)` | `None` | yes | no |
| `NOT(v < 5)` | `float("nan")` | yes | no |
| `NOT(v < 5)` | `Decimal("NaN")` | yes | no |
| `NOT(v < 5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v < 5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v < 5)` | `"2026-06-01"` | yes | no |
| `NOT(v < 5)` | `[5]` | yes | no |
| `NOT(v < 5)` | `(5,)` | yes | no |
| `NOT(v < 5)` | `{"a": 5}` | yes | no |
| `NOT(v < 5.5)` | `"5"` | yes | no |
| `NOT(v < 5.5)` | `"true"` | yes | no |
| `NOT(v < 5.5)` | `"abc"` | yes | no |
| `NOT(v < 5.5)` | `""` | yes | no |
| `NOT(v < 5.5)` | `None` | yes | no |
| `NOT(v < 5.5)` | `float("nan")` | yes | no |
| `NOT(v < 5.5)` | `Decimal("NaN")` | yes | no |
| `NOT(v < 5.5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v < 5.5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v < 5.5)` | `"2026-06-01"` | yes | no |
| `NOT(v < 5.5)` | `[5]` | yes | no |
| `NOT(v < 5.5)` | `(5,)` | yes | no |
| `NOT(v < 5.5)` | `{"a": 5}` | yes | no |
| `NOT(v < "5")` | `5` | yes | no |
| `NOT(v < "5")` | `0` | yes | no |
| `NOT(v < "5")` | `5.5` | yes | no |
| `NOT(v < "5")` | `Decimal("5.5")` | yes | no |
| `NOT(v < "5")` | `True` | yes | no |
| `NOT(v < "5")` | `False` | yes | no |
| `NOT(v < "5")` | `None` | yes | no |
| `NOT(v < "5")` | `float("nan")` | yes | no |
| `NOT(v < "5")` | `Decimal("NaN")` | yes | no |
| `NOT(v < "5")` | `float("inf")` | yes | no |
| `NOT(v < "5")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v < "5")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v < "5")` | `[5]` | yes | no |
| `NOT(v < "5")` | `(5,)` | yes | no |
| `NOT(v < "5")` | `{"a": 5}` | yes | no |
| `NOT(v < "abc")` | `5` | yes | no |
| `NOT(v < "abc")` | `0` | yes | no |
| `NOT(v < "abc")` | `5.5` | yes | no |
| `NOT(v < "abc")` | `Decimal("5.5")` | yes | no |
| `NOT(v < "abc")` | `True` | yes | no |
| `NOT(v < "abc")` | `False` | yes | no |
| `NOT(v < "abc")` | `None` | yes | no |
| `NOT(v < "abc")` | `float("nan")` | yes | no |
| `NOT(v < "abc")` | `Decimal("NaN")` | yes | no |
| `NOT(v < "abc")` | `float("inf")` | yes | no |
| `NOT(v < "abc")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v < "abc")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v < "abc")` | `[5]` | yes | no |
| `NOT(v < "abc")` | `(5,)` | yes | no |
| `NOT(v < "abc")` | `{"a": 5}` | yes | no |
| `NOT(v < True)` | `"5"` | yes | no |
| `NOT(v < True)` | `"true"` | yes | no |
| `NOT(v < True)` | `"abc"` | yes | no |
| `NOT(v < True)` | `""` | yes | no |
| `NOT(v < True)` | `None` | yes | no |
| `NOT(v < True)` | `float("nan")` | yes | no |
| `NOT(v < True)` | `Decimal("NaN")` | yes | no |
| `NOT(v < True)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v < True)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v < True)` | `"2026-06-01"` | yes | no |
| `NOT(v < True)` | `[5]` | yes | no |
| `NOT(v < True)` | `(5,)` | yes | no |
| `NOT(v < True)` | `{"a": 5}` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `5` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `0` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `5.5` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `Decimal("5.5")` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `True` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `False` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `"5"` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `"true"` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `"abc"` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `""` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `None` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `float("nan")` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `Decimal("NaN")` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `float("inf")` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `"2026-06-01"` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `[5]` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `(5,)` | yes | no |
| `NOT(v < date(2026, 1, 1))` | `{"a": 5}` | yes | no |
| `NOT(v < None)` | `5` | yes | no |
| `NOT(v < None)` | `0` | yes | no |
| `NOT(v < None)` | `5.5` | yes | no |
| `NOT(v < None)` | `Decimal("5.5")` | yes | no |
| `NOT(v < None)` | `True` | yes | no |
| `NOT(v < None)` | `False` | yes | no |
| `NOT(v < None)` | `"5"` | yes | no |
| `NOT(v < None)` | `"true"` | yes | no |
| `NOT(v < None)` | `"abc"` | yes | no |
| `NOT(v < None)` | `""` | yes | no |
| `NOT(v < None)` | `None` | yes | no |
| `NOT(v < None)` | `float("nan")` | yes | no |
| `NOT(v < None)` | `Decimal("NaN")` | yes | no |
| `NOT(v < None)` | `float("inf")` | yes | no |
| `NOT(v < None)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v < None)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v < None)` | `"2026-06-01"` | yes | no |
| `NOT(v < None)` | `[5]` | yes | no |
| `NOT(v < None)` | `(5,)` | yes | no |
| `NOT(v < None)` | `{"a": 5}` | yes | no |
| `NOT(v <= 5)` | `"5"` | yes | no |
| `NOT(v <= 5)` | `"true"` | yes | no |
| `NOT(v <= 5)` | `"abc"` | yes | no |
| `NOT(v <= 5)` | `""` | yes | no |
| `NOT(v <= 5)` | `None` | yes | no |
| `NOT(v <= 5)` | `float("nan")` | yes | no |
| `NOT(v <= 5)` | `Decimal("NaN")` | yes | no |
| `NOT(v <= 5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v <= 5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v <= 5)` | `"2026-06-01"` | yes | no |
| `NOT(v <= 5)` | `[5]` | yes | no |
| `NOT(v <= 5)` | `(5,)` | yes | no |
| `NOT(v <= 5)` | `{"a": 5}` | yes | no |
| `NOT(v <= 5.5)` | `"5"` | yes | no |
| `NOT(v <= 5.5)` | `"true"` | yes | no |
| `NOT(v <= 5.5)` | `"abc"` | yes | no |
| `NOT(v <= 5.5)` | `""` | yes | no |
| `NOT(v <= 5.5)` | `None` | yes | no |
| `NOT(v <= 5.5)` | `float("nan")` | yes | no |
| `NOT(v <= 5.5)` | `Decimal("NaN")` | yes | no |
| `NOT(v <= 5.5)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v <= 5.5)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v <= 5.5)` | `"2026-06-01"` | yes | no |
| `NOT(v <= 5.5)` | `[5]` | yes | no |
| `NOT(v <= 5.5)` | `(5,)` | yes | no |
| `NOT(v <= 5.5)` | `{"a": 5}` | yes | no |
| `NOT(v <= "5")` | `5` | yes | no |
| `NOT(v <= "5")` | `0` | yes | no |
| `NOT(v <= "5")` | `5.5` | yes | no |
| `NOT(v <= "5")` | `Decimal("5.5")` | yes | no |
| `NOT(v <= "5")` | `True` | yes | no |
| `NOT(v <= "5")` | `False` | yes | no |
| `NOT(v <= "5")` | `None` | yes | no |
| `NOT(v <= "5")` | `float("nan")` | yes | no |
| `NOT(v <= "5")` | `Decimal("NaN")` | yes | no |
| `NOT(v <= "5")` | `float("inf")` | yes | no |
| `NOT(v <= "5")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v <= "5")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v <= "5")` | `[5]` | yes | no |
| `NOT(v <= "5")` | `(5,)` | yes | no |
| `NOT(v <= "5")` | `{"a": 5}` | yes | no |
| `NOT(v <= "abc")` | `5` | yes | no |
| `NOT(v <= "abc")` | `0` | yes | no |
| `NOT(v <= "abc")` | `5.5` | yes | no |
| `NOT(v <= "abc")` | `Decimal("5.5")` | yes | no |
| `NOT(v <= "abc")` | `True` | yes | no |
| `NOT(v <= "abc")` | `False` | yes | no |
| `NOT(v <= "abc")` | `None` | yes | no |
| `NOT(v <= "abc")` | `float("nan")` | yes | no |
| `NOT(v <= "abc")` | `Decimal("NaN")` | yes | no |
| `NOT(v <= "abc")` | `float("inf")` | yes | no |
| `NOT(v <= "abc")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v <= "abc")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v <= "abc")` | `[5]` | yes | no |
| `NOT(v <= "abc")` | `(5,)` | yes | no |
| `NOT(v <= "abc")` | `{"a": 5}` | yes | no |
| `NOT(v <= True)` | `"5"` | yes | no |
| `NOT(v <= True)` | `"true"` | yes | no |
| `NOT(v <= True)` | `"abc"` | yes | no |
| `NOT(v <= True)` | `""` | yes | no |
| `NOT(v <= True)` | `None` | yes | no |
| `NOT(v <= True)` | `float("nan")` | yes | no |
| `NOT(v <= True)` | `Decimal("NaN")` | yes | no |
| `NOT(v <= True)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v <= True)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v <= True)` | `"2026-06-01"` | yes | no |
| `NOT(v <= True)` | `[5]` | yes | no |
| `NOT(v <= True)` | `(5,)` | yes | no |
| `NOT(v <= True)` | `{"a": 5}` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `5` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `0` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `5.5` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `Decimal("5.5")` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `True` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `False` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `"5"` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `"true"` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `"abc"` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `""` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `None` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `float("nan")` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `Decimal("NaN")` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `float("inf")` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `"2026-06-01"` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `[5]` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `(5,)` | yes | no |
| `NOT(v <= date(2026, 1, 1))` | `{"a": 5}` | yes | no |
| `NOT(v <= None)` | `5` | yes | no |
| `NOT(v <= None)` | `0` | yes | no |
| `NOT(v <= None)` | `5.5` | yes | no |
| `NOT(v <= None)` | `Decimal("5.5")` | yes | no |
| `NOT(v <= None)` | `True` | yes | no |
| `NOT(v <= None)` | `False` | yes | no |
| `NOT(v <= None)` | `"5"` | yes | no |
| `NOT(v <= None)` | `"true"` | yes | no |
| `NOT(v <= None)` | `"abc"` | yes | no |
| `NOT(v <= None)` | `""` | yes | no |
| `NOT(v <= None)` | `None` | yes | no |
| `NOT(v <= None)` | `float("nan")` | yes | no |
| `NOT(v <= None)` | `Decimal("NaN")` | yes | no |
| `NOT(v <= None)` | `float("inf")` | yes | no |
| `NOT(v <= None)` | `date(2026, 6, 1)` | yes | no |
| `NOT(v <= None)` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v <= None)` | `"2026-06-01"` | yes | no |
| `NOT(v <= None)` | `[5]` | yes | no |
| `NOT(v <= None)` | `(5,)` | yes | no |
| `NOT(v <= None)` | `{"a": 5}` | yes | no |
| `NOT(v contains "a")` | `5` | yes | no |
| `NOT(v contains "a")` | `0` | yes | no |
| `NOT(v contains "a")` | `5.5` | yes | no |
| `NOT(v contains "a")` | `Decimal("5.5")` | yes | no |
| `NOT(v contains "a")` | `True` | yes | no |
| `NOT(v contains "a")` | `False` | yes | no |
| `NOT(v contains "a")` | `float("nan")` | yes | no |
| `NOT(v contains "a")` | `Decimal("NaN")` | yes | no |
| `NOT(v contains "a")` | `float("inf")` | yes | no |
| `NOT(v contains "a")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v contains "a")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v contains "5")` | `5` | yes | no |
| `NOT(v contains "5")` | `0` | yes | no |
| `NOT(v contains "5")` | `5.5` | yes | no |
| `NOT(v contains "5")` | `Decimal("5.5")` | yes | no |
| `NOT(v contains "5")` | `True` | yes | no |
| `NOT(v contains "5")` | `False` | yes | no |
| `NOT(v contains "5")` | `float("nan")` | yes | no |
| `NOT(v contains "5")` | `Decimal("NaN")` | yes | no |
| `NOT(v contains "5")` | `float("inf")` | yes | no |
| `NOT(v contains "5")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v contains "5")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v contains "(")` | `5` | yes | no |
| `NOT(v contains "(")` | `0` | yes | no |
| `NOT(v contains "(")` | `5.5` | yes | no |
| `NOT(v contains "(")` | `Decimal("5.5")` | yes | no |
| `NOT(v contains "(")` | `True` | yes | no |
| `NOT(v contains "(")` | `False` | yes | no |
| `NOT(v contains "(")` | `float("nan")` | yes | no |
| `NOT(v contains "(")` | `Decimal("NaN")` | yes | no |
| `NOT(v contains "(")` | `float("inf")` | yes | no |
| `NOT(v contains "(")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v contains "(")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v not_contains "a")` | `5` | yes | no |
| `NOT(v not_contains "a")` | `0` | yes | no |
| `NOT(v not_contains "a")` | `5.5` | yes | no |
| `NOT(v not_contains "a")` | `Decimal("5.5")` | yes | no |
| `NOT(v not_contains "a")` | `True` | yes | no |
| `NOT(v not_contains "a")` | `False` | yes | no |
| `NOT(v not_contains "a")` | `float("nan")` | yes | no |
| `NOT(v not_contains "a")` | `Decimal("NaN")` | yes | no |
| `NOT(v not_contains "a")` | `float("inf")` | yes | no |
| `NOT(v not_contains "a")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v not_contains "a")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v not_contains "5")` | `5` | yes | no |
| `NOT(v not_contains "5")` | `0` | yes | no |
| `NOT(v not_contains "5")` | `5.5` | yes | no |
| `NOT(v not_contains "5")` | `Decimal("5.5")` | yes | no |
| `NOT(v not_contains "5")` | `True` | yes | no |
| `NOT(v not_contains "5")` | `False` | yes | no |
| `NOT(v not_contains "5")` | `float("nan")` | yes | no |
| `NOT(v not_contains "5")` | `Decimal("NaN")` | yes | no |
| `NOT(v not_contains "5")` | `float("inf")` | yes | no |
| `NOT(v not_contains "5")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v not_contains "5")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v not_contains "(")` | `5` | yes | no |
| `NOT(v not_contains "(")` | `0` | yes | no |
| `NOT(v not_contains "(")` | `5.5` | yes | no |
| `NOT(v not_contains "(")` | `Decimal("5.5")` | yes | no |
| `NOT(v not_contains "(")` | `True` | yes | no |
| `NOT(v not_contains "(")` | `False` | yes | no |
| `NOT(v not_contains "(")` | `float("nan")` | yes | no |
| `NOT(v not_contains "(")` | `Decimal("NaN")` | yes | no |
| `NOT(v not_contains "(")` | `float("inf")` | yes | no |
| `NOT(v not_contains "(")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v not_contains "(")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v regex "(")` | `5` | yes | no |
| `NOT(v regex "(")` | `0` | yes | no |
| `NOT(v regex "(")` | `5.5` | yes | no |
| `NOT(v regex "(")` | `Decimal("5.5")` | yes | no |
| `NOT(v regex "(")` | `True` | yes | no |
| `NOT(v regex "(")` | `False` | yes | no |
| `NOT(v regex "(")` | `"5"` | yes | no |
| `NOT(v regex "(")` | `"true"` | yes | no |
| `NOT(v regex "(")` | `"abc"` | yes | no |
| `NOT(v regex "(")` | `""` | yes | no |
| `NOT(v regex "(")` | `float("nan")` | yes | no |
| `NOT(v regex "(")` | `Decimal("NaN")` | yes | no |
| `NOT(v regex "(")` | `float("inf")` | yes | no |
| `NOT(v regex "(")` | `date(2026, 6, 1)` | yes | no |
| `NOT(v regex "(")` | `datetime(2026, 6, 1, 12, 0)` | yes | no |
| `NOT(v regex "(")` | `"2026-06-01"` | yes | no |
| `NOT(v regex "(")` | `[5]` | yes | no |
| `NOT(v regex "(")` | `(5,)` | yes | no |
| `NOT(v regex "(")` | `{"a": 5}` | yes | no |

### `uncomparable=false`

`EngineConfig(uncomparable="false")` keeps the default answers and turns off the `ComparisonWarning`. The issues are still listed in the result.

With the matrix's rules and facts, this setting changes no answers.

## Known differences between paths

None. Every evaluation path gives the answers above under every setting: `PhreakEngine` with and without the alpha prefilter, compiled conditions, streaming mode, the thread pool, `evaluate_batch` in this process and over worker processes, `fluxrules.evaluate()`, `CrossFactEngine` (for the rules it can express), `PreFilteredEvaluator` over a SQL fact store, the CLI and the HTTP API. The answers are also the same whether a rule is written as a dict, as an `F` expression or in a YAML file. The tests fail if any of them starts to differ.

## Avoiding surprises

- **Give the engine a fact schema.** With `fact_schema=` and `validate_facts="normalize"`, the text `"100.3"` becomes the number `100.3` before any rule runs; with `validate_facts="strict"`, a wrong type raises `FactValidationError` instead of quietly not matching. See [Typed Facts](typed-facts.md).
- **Or convert in a pipeline.** The `FieldType` transform converts named fields of a plain dict. See [Fact Pipeline](fact-pipeline.md).
- **Use `Decimal` for money,** and avoid `==` on floats: compare with `>=` or `<=` instead.
- **Parse dates first.** An ISO date string is text, and a `date` does not compare with a `datetime`.
- **Write `in` values as a list,** and use `==` when you mean one value.
- **Check rules before they run.** With a fact schema, `load_rules` refuses a rule value of the wrong type for its field, such as the text `"100.1"` for a `float` field, and loads an ISO date string on a `date` field as a date. `fluxrules.validate()` and `fluxrules validate` list every such problem. See [Rule values are checked too](typed-facts.md#rule-values-are-checked-too).
