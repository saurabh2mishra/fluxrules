# Contributing to FluxRules

Thank you for contributing to FluxRules.

This project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By
participating, you are expected to uphold it.

## Development Setup

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) **0.8.0 or newer**

FluxRules uses the revision-2 `uv.lock` format. Older uv versions fail before
dependency installation begins. Check the version before running any project
command:

```bash
python scripts/check_uv.py
```

If uv is missing or older than 0.8.0, install or upgrade it, then rerun the check:

```bash
python -m pip install 'uv>=0.8'
```

### Install

```bash
git clone https://github.com/saurabh2mishra/fluxrules.git
cd fluxrules
unset VIRTUAL_ENV
python scripts/check_uv.py
uv sync --extra dev
```

The project uses the root `.venv`. If you intentionally use another active
environment, use `uv run --active <command>` or `uv pip install --active ...`
to target it.

## Common Commands

```bash
make lint
make type-check
make test
make docs
```

## Testing

Run all tests:

```bash
uv run pytest tests/ -v
```

Run coverage:

```bash
uv run pytest tests/ --cov=src/fluxrules --cov-report=term-missing
```

## Contributing a Change

All changes land through pull requests. The `main` branch does not accept direct
pushes from contributors — only the project maintainer can merge or commit to it.

**Workflow:**

```bash
# 1. Fork the repo (first-time contributors) or sync your fork
git checkout main && git pull origin main

# 2. Create a feature branch — never commit directly to main
git checkout -b feature/my-change

# 3. Make changes, then verify locally before pushing
make lint
make type-check
make test

# 4. Push your branch and open a pull request
git push origin feature/my-change
# → open a PR on GitHub targeting main
```

The PR must pass all CI checks and receive an approving review from the
maintainer before it can be merged.

## Pull Requests

Please keep pull requests focused and include:

- a clear problem statement
- tests for behavior changes
- docs updates for public API or workflow changes

Before opening a PR, ensure linting, typing, tests, and docs build pass locally.

## Branch Protection

`main` is protected. Merges require:

- A green CI run — all required checks (`lint`, `test` matrix, `type-check`,
  `docs-execute`, `clean-install`, `build-smoke`, `examples`, `security`, and
  `dependency-review` on PRs) must pass.
- At least one approving review, including [Code Owner](.github/CODEOWNERS)
  approval for the paths a PR touches.
- An up-to-date branch (rebased on latest `main`).

Direct pushes and force-pushes to `main` are disabled; changes land through pull
requests. Releases are tagged `vX.Y.Z` (matching `__version__`) and published by
the signed [release workflow](.github/workflows/release.yml).

## Reporting Issues

Use GitHub issues for bugs and feature requests.

For security reports, see [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
