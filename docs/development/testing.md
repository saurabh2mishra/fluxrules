# Testing

How to run the tests, how they are organized, and the checks a change must
pass before it is merged.

## Run the tests

The `make` targets run everything through uv, so they use the project
environment:

| Command | What it runs |
|---|---|
| `make test-full` | Every test except benchmarks, in parallel. Run this before a pull request. |
| `make test-fast` | `tests/unit` and `tests/integration` only, in parallel. |
| `make test` | Every test except benchmarks, one at a time, with each test named. |
| `make test-cov` | Every test, with line coverage of `src/fluxrules`. |
| `make test-examples` | The example scripts in `examples/`. |
| `make test-perf` | The benchmarks only (tests marked `performance`). |

To run one file or one test, call pytest directly:

```bash
uv run pytest tests/engine/test_comparison_matrix.py
uv run pytest tests/unit/test_membership_value.py -k "single_dict"
```

## How the tests are organized

| Folder | What it tests |
|---|---|
| `tests/unit` | One module or function at a time. |
| `tests/engine` | The engines: PHREAK, streaming, batches and the comparison matrix. |
| `tests/prefilter` | The alpha prefilter and the SQL fact store. |
| `tests/api` | The HTTP API. |
| `tests/integration` | Several parts working together, end to end. |
| `tests/contract` | What the public API and every engine promise, including the quickstart. |
| `tests/docs` | The code snippets in the docs, and generated pages being up to date. |
| `tests/examples` | The scripts in `examples/`. |
| `tests/regression` | Behaviour that once broke, so it cannot break again. |
| `tests/security` | Hardening against bad input and failures. |
| `tests/performance` | Benchmarks, marked `performance` and skipped by default. |
| `tests/infrastructure` | Engine memory: the node cache and the working-memory watchdog. |
| `tests/observability` | Engine metrics. |
| `tests/plugins` | Actions and the action registry. |

## The comparison matrix

FluxRules can evaluate a rule in many ways: `PhreakEngine` with or without the
alpha prefilter, compiled conditions, streaming mode, the thread pool,
`evaluate_batch` (also over worker processes), `fluxrules.evaluate()`,
`CrossFactEngine`, `PreFilteredEvaluator`, the CLI and the HTTP API. A rule can also be written
as a dict, as an `F` expression or in a YAML file. All of these must give the
same answer.

`tests/engine/comparison_matrix.py` checks that. It builds a rule for every
operator and rule value, plain and wrapped in `NOT`, `AND` and `OR`, evaluates
each one against about twenty kinds of fact value (numbers, text, `None`,
`NaN`, dates, lists, tuples, a missing field and more), under each comparison
setting, on every path. `tests/engine/test_comparison_matrix.py` fails when
any path differs from `PhreakEngine` without the prefilter in any of three
things:

- which rules fired;
- the `comparison_issues` it lists, for paths that list them;
- whether it raised `UncomparableValuesError` under
  `EngineConfig(uncomparable="raise")`.

Each wrapper (plain, `NOT`, `AND`, `OR`) is evaluated in its own engine. An
issue does not say which rule it came from, so in one engine a `NOT` rule
would report the same issue as its plain twin. The alpha prefilter never skips
a `NOT` rule, so a prefilter that wrongly skipped the plain rule would go
unnoticed.

`tests/engine/test_mixed_type_fuzz.py` does the same with random rule trees
over several fields. It runs 60 random examples by default; set
`FLUXRULES_FUZZ_EXAMPLES` for a longer run:

```bash
FLUXRULES_FUZZ_EXAMPLES=1000 uv run pytest tests/engine/test_mixed_type_fuzz.py -n auto
```

The [How FluxRules Compares Values](../comparing-values.md) page is generated
from the matrix. After any change to how values compare, regenerate it and
commit the result:

```bash
make docs-tables
```

`tests/docs/test_comparing_values_page.py` fails when the committed page is
out of date.

When you add an operator or an evaluation path, add it to the matrix too.
`test_the_matrix_covers_every_path_setting_and_operator` fails when an
operator is missing.

## Checks before a pull request

CI runs these on Python 3.11 to 3.14. Run them locally first:

```bash
make lint          # ruff check
make type-check    # mypy
make test-full     # tests
make docs          # strict docs build: broken links and anchors fail
```

## Test standards

- Add a test for every new feature, and a regression test for every bug fix.
- When a change alters behaviour, update the tests that describe it.
- Keep coverage of new code high. Codecov reports coverage of the lines each
  pull request changes.
- Use fixtures for shared setup, and restore any process-wide setting (such
  as `set_config`) that a test changes.
