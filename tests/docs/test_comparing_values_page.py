"""docs/comparing-values.md is exactly what the comparison matrix renders.

The page is generated from tests/engine/comparison_matrix.py. If this fails,
the code and the page disagree: run ``make docs-tables`` and commit the page.
"""

from __future__ import annotations

from tests.engine.comparison_page import PAGE, render


def test_page_matches_the_matrix():
    assert PAGE.exists(), "docs/comparing-values.md is missing: run `make docs-tables`"
    assert PAGE.read_text() == render(), (
        "docs/comparing-values.md is out of date: run `make docs-tables` and commit it"
    )
