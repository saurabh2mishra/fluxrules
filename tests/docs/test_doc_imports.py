"""Check 1 - every documented ``fluxrules`` import resolves.

Fast and precise: resolves the module and asserts the attribute exists.
This is the check that catches the refactor drift (``engines``->``engine``,
``Rule``->``EngineRule``) that the unit tests cannot see.

The known-broken baseline lives in ``BASELINE_BROKEN``. The test asserts the
count never *grows*, and tells you to lower the baseline when you fix things.
"""

from __future__ import annotations

import importlib

import pytest

from tests.docs._extract import DocImport, extract_imports, markdown_files

# Baseline of currently-broken documented imports. MUST only ever decrease.
# Step 8 drove this to zero, so the check is now fully blocking: any new
# documented import that does not resolve fails CI.
BASELINE_BROKEN = 0


def _all_imports() -> list[DocImport]:
    found: list[DocImport] = []
    for path in markdown_files():
        found.extend(extract_imports(path))
    return found


def _resolve(imp: DocImport) -> str | None:
    """Return an error string if the import does not resolve, else None."""
    try:
        module = importlib.import_module(imp.module)
    except Exception as exc:
        return f"{imp.rel}:{imp.line}: {imp} -> {type(exc).__name__}: {exc}"

    if imp.name is None:
        return None

    if not hasattr(module, imp.name):
        # `from pkg import submodule` is valid even without an attribute.
        try:
            importlib.import_module(f"{imp.module}.{imp.name}")
        except Exception:
            return f"{imp.rel}:{imp.line}: {imp} -> {imp.module!r} has no attribute {imp.name!r}"

    return None


def test_documented_imports_resolve() -> None:
    """Every ``fluxrules`` import appearing in the docs must resolve."""
    imports = _all_imports()
    assert imports, "extractor found no imports - the harness itself is broken"

    broken = [err for imp in imports for err in (_resolve(imp),) if err]

    total = len(imports)
    ok = total - len(broken)
    print(f"\ndocs import check: {ok}/{total} resolve, {len(broken)} BROKEN")
    for err in broken:
        print(f"  {err}")

    if len(broken) > BASELINE_BROKEN:
        pytest.fail(
            f"{len(broken)} broken documented imports, baseline is {BASELINE_BROKEN}.\n"
            + "\n".join(broken)
        )

    if len(broken) < BASELINE_BROKEN:
        pytest.fail(
            f"Only {len(broken)} broken imports remain (baseline {BASELINE_BROKEN}). "
            f"Lower BASELINE_BROKEN to {len(broken)} to lock in the improvement."
        )
